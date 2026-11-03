import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:unorm_dart/unorm_dart.dart' as unorm;

class DigestAuthService {
  static final RegExp _sha256Pattern = RegExp(r'^[0-9a-fA-F]{64}$');

  static final RegExp _nonceCountPattern = RegExp(r'^[0-9a-fA-F]{8}$');

  // Calculate HA1 from username, realm, and password.
  static String calculateHa1({
    required String username,
    required String password,
    required String realm,
  }) {
    if (username.isEmpty || password.isEmpty || realm.isEmpty) {
      throw ArgumentError('Username, password, and realm are required.');
    }

    final normalizedUsername = unorm.nfc(username);
    final normalizedPassword = unorm.nfc(password);

    final input = '$normalizedUsername:$realm:$normalizedPassword';

    return sha256.convert(utf8.encode(input)).toString();
  }

  // Calculate HA2 from HTTP method and request URI.
  static String calculateHa2({
    required String method,
    required String requestUri,
  }) {
    if (method.isEmpty || requestUri.isEmpty) {
      throw ArgumentError('HTTP method and request URI are required.');
    }

    final input = '$method:$requestUri';

    return sha256.convert(utf8.encode(input)).toString();
  }

  // Calculate the final HTTP Digest response.
  static String calculateResponse({
    required String ha1,
    required String nonce,
    required String nonceCount,
    required String clientNonce,
    required String qop,
    required String ha2,
  }) {
    if (!_sha256Pattern.hasMatch(ha1)) {
      throw ArgumentError('Invalid HA1 value.');
    }

    if (!_sha256Pattern.hasMatch(ha2)) {
      throw ArgumentError('Invalid HA2 value.');
    }

    if (nonce.isEmpty || clientNonce.isEmpty) {
      throw ArgumentError('Nonce values must not be empty.');
    }

    if (!_nonceCountPattern.hasMatch(nonceCount)) {
      throw ArgumentError('Invalid nonce count.');
    }

    if (int.parse(nonceCount, radix: 16) == 0) {
      throw ArgumentError('Nonce count must be greater than zero.');
    }

    if (qop != 'auth') {
      throw ArgumentError('Unsupported quality of protection.');
    }

    final input = '$ha1:$nonce:$nonceCount:$clientNonce:$qop:$ha2';

    return sha256.convert(utf8.encode(input)).toString();
  }
}
