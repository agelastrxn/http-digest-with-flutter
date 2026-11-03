import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/digest_auth_service.dart';

void main() {
  group('DigestAuthService', () {
    test('calculates RFC 7616 SHA-256 response correctly', () {
      final ha1 = DigestAuthService.calculateHa1(
        username: 'Mufasa',
        realm: 'http-auth@example.org',
        password: 'Circle of Life',
      );

      final ha2 = DigestAuthService.calculateHa2(
        method: 'GET',
        requestUri: '/dir/index.html',
      );

      final response = DigestAuthService.calculateResponse(
        ha1: ha1,
        nonce: '7ypf/xlj9XXwfDPEoM4URrv/xwf94BcCAzFZH4GiTo0v',
        nonceCount: '00000001',
        clientNonce: 'f2/wE4q74E6zIJEtWaHKaf5wv/H5QzzpXusqGemxURZJ',
        qop: 'auth',
        ha2: ha2,
      );

      expect(
        response,
        '753927fa0e85d155564e2e272a28d1802ca10daf4496794697cf8db5856cb6c1',
      );
    });

    test('normalizes Unicode username and password using NFC', () {
      final firstHa1 = DigestAuthService.calculateHa1(
        username: 'Jose\u0301',
        realm: 'test-realm',
        password: 'test-password',
      );

      final secondHa1 = DigestAuthService.calculateHa1(
        username: 'Jos\u00e9',
        realm: 'test-realm',
        password: 'test-password',
      );

      expect(firstHa1, secondHa1);
    });

    test('rejects invalid nonce count', () {
      expect(
        () => DigestAuthService.calculateResponse(
          ha1: 'a' * 64,
          nonce: 'test-nonce',
          nonceCount: '00000000',
          clientNonce: 'client-test',
          qop: 'auth',
          ha2: 'b' * 64,
        ),
        throwsArgumentError,
      );
    });
  });
}
