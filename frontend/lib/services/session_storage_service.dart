import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SessionStorageService {
  static const String _sessionTokenKey = 'auth_session_token';

  static final FlutterSecureStorage _storage = FlutterSecureStorage();

  // Save the session token securely.
  Future<void> saveToken(String token) async {
    if (token.trim().isEmpty) {
      throw ArgumentError('Session token cannot be empty.');
    }

    await _storage.write(key: _sessionTokenKey, value: token);
  }

  // Read the saved session token.
  Future<String?> getToken() async {
    return await _storage.read(key: _sessionTokenKey);
  }

  // Check whether a session token exists.
  Future<bool> hasToken() async {
    final token = await getToken();

    return token != null && token.isNotEmpty;
  }

  // Delete the session token.
  Future<void> deleteToken() async {
    await _storage.delete(key: _sessionTokenKey);
  }
}
