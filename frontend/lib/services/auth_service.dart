import 'dart:convert';
import 'dart:math';

import '../core/config/api_config.dart';
import 'digest_auth_service.dart';
import 'session_storage_service.dart';

import 'package:http/http.dart' as http;

class AuthService {
  final http.Client _client;
  final SessionStorageService _sessionStorage;

  AuthService({http.Client? client, SessionStorageService? sessionStorage})
    : _client = client ?? http.Client(),
      _sessionStorage = sessionStorage ?? SessionStorageService();

  // Register a new user account.
  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
  }) async {
    final normalizedUsername = username.trim().toLowerCase();

    if (normalizedUsername.isEmpty || password.isEmpty) {
      throw ArgumentError('Username and password are required.');
    }

    final uri = ApiConfig.endpoint(ApiConfig.registerEndpoint);

    final response = await _client.post(
      uri,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'username': normalizedUsername, 'password': password}),
    );

    final responseData = _decodeJsonResponse(response.body);

    if (response.statusCode != 201) {
      throw Exception(responseData['error'] ?? 'Registration failed.');
    }

    return responseData;
  }

  // Authenticate a user using HTTP Digest Authentication.
  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    final normalizedUsername = username.trim().toLowerCase();

    if (normalizedUsername.isEmpty || password.isEmpty) {
      throw ArgumentError('Username and password are required.');
    }

    final loginUri = ApiConfig.endpoint(ApiConfig.digestLoginEndpoint);

    // Step 1: Request a Digest challenge from Flask.
    final challengeResponse = await _client.post(loginUri);

    if (challengeResponse.statusCode != 401) {
      throw Exception(
        'Unexpected challenge response: ${challengeResponse.statusCode}',
      );
    }

    // Step 2: Read the WWW-Authenticate header.
    final challengeHeader = _getHeader(
      challengeResponse.headers,
      'www-authenticate',
    );

    if (challengeHeader == null || challengeHeader.isEmpty) {
      throw Exception('Digest challenge header is missing.');
    }

    // Step 3: Parse the challenge parameters.
    final challenge = _parseDigestChallenge(challengeHeader);

    final realm = challenge['realm']!;
    final nonce = challenge['nonce']!;
    final algorithm = challenge['algorithm']!;
    final qop = challenge['qop']!;

    if (algorithm.toUpperCase() != 'SHA-256') {
      throw Exception('Unsupported Digest algorithm.');
    }

    if (qop != 'auth') {
      throw Exception('Unsupported Digest quality of protection.');
    }

    // Step 4: Prepare HTTP request information.
    const method = 'POST';

    final requestUri =
        loginUri.path + (loginUri.hasQuery ? '?${loginUri.query}' : '');

    const nonceCount = '00000001';

    final clientNonce = _generateClientNonce();

    // Step 5: Calculate HA1.
    final ha1 = DigestAuthService.calculateHa1(
      username: normalizedUsername,
      realm: realm,
      password: password,
    );

    // Step 6: Calculate HA2.
    final ha2 = DigestAuthService.calculateHa2(
      method: method,
      requestUri: requestUri,
    );

    // Step 7: Calculate the final Digest response.
    final responseHash = DigestAuthService.calculateResponse(
      ha1: ha1,
      nonce: nonce,
      nonceCount: nonceCount,
      clientNonce: clientNonce,
      qop: qop,
      ha2: ha2,
    );

    // Step 8: Build the Authorization header.
    final authorizationHeader =
        'Digest username="${_escapeQuoted(normalizedUsername)}", '
        'realm="${_escapeQuoted(realm)}", '
        'nonce="${_escapeQuoted(nonce)}", '
        'uri="${_escapeQuoted(requestUri)}", '
        'algorithm=$algorithm, '
        'qop=$qop, '
        'nc=$nonceCount, '
        'cnonce="${_escapeQuoted(clientNonce)}", '
        'response="$responseHash"';

    // Step 9: Send the authenticated POST request.
    final authenticatedResponse = await _client.post(
      loginUri,
      headers: {
        'Authorization': authorizationHeader,
        'Accept': 'application/json',
      },
    );

    final responseData = _decodeJsonResponse(authenticatedResponse.body);

    if (authenticatedResponse.statusCode != 200) {
      throw Exception(responseData['error'] ?? 'Authentication failed.');
    }

    // Step 10: Extract and save the session token.
    final sessionToken = responseData['session_token'];

    if (sessionToken is! String || sessionToken.isEmpty) {
      throw Exception('Session token was not returned.');
    }

    await _sessionStorage.saveToken(sessionToken);

    return responseData;
  }

  // Parse the server's WWW-Authenticate challenge.
  Map<String, String> _parseDigestChallenge(String header) {
    if (!header.trim().toLowerCase().startsWith('digest ')) {
      throw FormatException('Invalid Digest challenge scheme.');
    }

    final parameters = <String, String>{};

    final pattern = RegExp(
      r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*("(?:\\.|[^"\\])*"|[^,\s]+)',
    );

    for (final match in pattern.allMatches(header)) {
      final key = match.group(1)!.toLowerCase();
      var value = match.group(2)!;

      if (parameters.containsKey(key)) {
        throw FormatException('Duplicate challenge parameter: $key');
      }

      if (value.startsWith('"') && value.endsWith('"')) {
        value = value.substring(1, value.length - 1);
      }

      parameters[key] = value;
    }

    const requiredFields = ['realm', 'nonce', 'algorithm', 'qop'];

    for (final field in requiredFields) {
      if (parameters[field] == null || parameters[field]!.isEmpty) {
        throw FormatException('Missing challenge parameter: $field');
      }
    }

    return parameters;
  }

  // Generate a cryptographically secure client nonce.
  String _generateClientNonce() {
    final random = Random.secure();

    final bytes = List<int>.generate(16, (_) => random.nextInt(256));

    return bytes.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  }

  // Escape values used inside quoted HTTP header parameters.
  String _escapeQuoted(String value) {
    return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  }

  // Read HTTP headers without depending on their letter casing.
  String? _getHeader(Map<String, String> headers, String name) {
    for (final entry in headers.entries) {
      if (entry.key.toLowerCase() == name.toLowerCase()) {
        return entry.value;
      }
    }

    return null;
  }

  // Decode a JSON response safely.
  Map<String, dynamic> _decodeJsonResponse(String body) {
    final decoded = jsonDecode(body);

    if (decoded is! Map) {
      throw FormatException('Invalid JSON response from server.');
    }

    return Map<String, dynamic>.from(decoded);
  }

  // Retrieve the authenticated user's profile.
  Future<Map<String, dynamic>> getProfile() async {
    final token = await _sessionStorage.getToken();

    if (token == null || token.isEmpty) {
      throw Exception('No active session found.');
    }

    final response = await _client.get(
      ApiConfig.endpoint(ApiConfig.profileEndpoint),
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    final data = _decodeJsonResponse(response.body);

    if (response.statusCode == 401) {
      await _sessionStorage.deleteToken();
      throw Exception('Session expired. Please sign in again.');
    }

    if (response.statusCode != 200) {
      throw Exception(data['error'] ?? 'Failed to retrieve user profile.');
    }

    return data;
  }

  // Log out and revoke the current server session.
  Future<void> logout() async {
    final token = await _sessionStorage.getToken();

    if (token == null || token.isEmpty) {
      return;
    }

    final response = await _client.post(
      ApiConfig.endpoint(ApiConfig.logoutEndpoint),
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    if (response.statusCode == 200 || response.statusCode == 401) {
      await _sessionStorage.deleteToken();
      return;
    }

    final data = _decodeJsonResponse(response.body);

    throw Exception(data['error'] ?? 'Logout failed.');
  }

  // Change the authenticated user's password.
  Future<Map<String, dynamic>> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    if (currentPassword.isEmpty || newPassword.isEmpty) {
      throw ArgumentError('Both passwords are required.');
    }

    if (newPassword.length < 12 || newPassword.length > 128) {
      throw ArgumentError(
        'New password must be between 12 and 128 characters.',
      );
    }

    final token = await _sessionStorage.getToken();

    if (token == null || token.isEmpty) {
      throw Exception('No active session found.');
    }

    final response = await _client.post(
      ApiConfig.endpoint(ApiConfig.changePasswordEndpoint),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'current_password': currentPassword,
        'new_password': newPassword,
      }),
    );

    final data = _decodeJsonResponse(response.body);

    if (response.statusCode != 200) {
      throw Exception(data['error'] ?? 'Password change failed.');
    }

    // The backend invalidates all existing sessions after a password change.
    await _sessionStorage.deleteToken();

    return data;
  }

  // Generate backup codes for the authenticated user.
  Future<List<String>> generateBackupCodes({
    required String currentPassword,
  }) async {
    if (currentPassword.isEmpty) {
      throw ArgumentError('Current password is required.');
    }

    final token = await _sessionStorage.getToken();

    if (token == null || token.isEmpty) {
      throw Exception('No active session found.');
    }

    final response = await _client.post(
      ApiConfig.endpoint(ApiConfig.backupCodesEndpoint),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'current_password': currentPassword}),
    );

    final data = _decodeJsonResponse(response.body);

    if (response.statusCode != 201) {
      throw Exception(data['error'] ?? 'Backup code generation failed.');
    }

    final codes = data['backup_codes'];

    if (codes is! List || codes.length != 10) {
      throw FormatException('Invalid backup code response.');
    }

    if (!codes.every((code) => code is String && code.isNotEmpty)) {
      throw FormatException('Invalid backup code format.');
    }

    return codes.cast<String>();
  }

  // Authenticate using a one-time backup code.
  Future<Map<String, dynamic>> backupLogin({
    required String username,
    required String backupCode,
  }) async {
    final normalizedUsername = username.trim().toLowerCase();
    final normalizedCode = backupCode.trim();

    if (normalizedUsername.isEmpty || normalizedCode.isEmpty) {
      throw ArgumentError('Username and backup code are required.');
    }

    final response = await _client.post(
      ApiConfig.endpoint(ApiConfig.backupLoginEndpoint),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'username': normalizedUsername,
        'backup_code': normalizedCode,
      }),
    );

    final data = _decodeJsonResponse(response.body);

    if (response.statusCode != 200) {
      throw Exception(data['error'] ?? 'Backup login failed.');
    }

    final sessionToken = data['session_token'];

    if (sessionToken is! String || sessionToken.isEmpty) {
      throw FormatException('Session token was not returned.');
    }

    await _sessionStorage.saveToken(sessionToken);

    return data;
  }

  // Recover an account using a one-time backup code.
  Future<Map<String, dynamic>> recoverAccount({
    required String username,
    required String backupCode,
    required String newPassword,
  }) async {
    final normalizedUsername = username.trim().toLowerCase();
    final normalizedCode = backupCode.trim();

    if (normalizedUsername.isEmpty ||
        normalizedCode.isEmpty ||
        newPassword.isEmpty) {
      throw ArgumentError(
        'Username, backup code, and new password are required.',
      );
    }

    if (newPassword.length < 12 || newPassword.length > 128) {
      throw ArgumentError(
        'New password must be between 12 and 128 characters.',
      );
    }

    final response = await _client.post(
      ApiConfig.endpoint(ApiConfig.recoverEndpoint),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'username': normalizedUsername,
        'backup_code': normalizedCode,
        'new_password': newPassword,
      }),
    );

    final data = _decodeJsonResponse(response.body);

    if (response.statusCode != 200) {
      throw Exception(data['error'] ?? 'Account recovery failed.');
    }

    // Remove any previously saved, now-invalid session.
    await _sessionStorage.deleteToken();

    return data;
  }

  // Close the HTTP client when it is no longer needed.
  void dispose() {
    _client.close();
  }
}
