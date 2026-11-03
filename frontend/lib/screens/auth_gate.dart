import 'package:flutter/material.dart';

import '../services/auth_service.dart';
import '../services/session_storage_service.dart';

import 'dashboard_screen.dart';
import 'login_screen.dart';

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final AuthService _authService = AuthService();

  final SessionStorageService _sessionStorage = SessionStorageService();

  bool _isChecking = true;
  bool _showLogin = false;

  String? _username;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();

    _restoreSession();
  }

  // Restore the existing session when the application starts.
  Future<void> _restoreSession() async {
    setState(() {
      _isChecking = true;
      _errorMessage = null;
    });

    String? restoredUsername;
    String? errorMessage;
    bool showLogin = false;

    try {
      // Verify the saved token with the Flask backend.
      final profile = await _authService.getProfile();

      final username = profile['username'];

      if (username is! String || username.isEmpty) {
        throw FormatException('Invalid profile response.');
      }

      restoredUsername = username;
    } catch (error) {
      try {
        // Check whether a token still exists.
        final token = await _sessionStorage.getToken();

        if (token == null || token.isEmpty) {
          // No valid saved token exists.
          showLogin = true;
        } else {
          // The backend could not verify the existing token.
          // Keep it so the user can retry when the server is available.
          errorMessage =
              'Unable to verify your session. '
              'Check your connection and try again.';
        }
      } catch (_) {
        errorMessage = 'Unable to access secure session storage.';
      }
    }

    if (!mounted) return;

    setState(() {
      _username = restoredUsername;
      _errorMessage = errorMessage;
      _showLogin = showLogin;
      _isChecking = false;
    });
  }

  void _continueToLogin() {
    setState(() {
      _showLogin = true;
      _errorMessage = null;
    });
  }

  @override
  void dispose() {
    _authService.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Show a loading screen while checking the session.
    if (_isChecking) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 20),
              Text('Restoring your session...'),
            ],
          ),
        ),
      );
    }

    // A valid session was restored.
    if (_username != null) {
      return DashboardScreen(username: _username!);
    }

    // The backend is unavailable or session verification failed.
    if (_errorMessage != null) {
      return Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.cloud_off_outlined,
                        size: 52,
                        color: Colors.orange,
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        'Session Verification Failed',
                        style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(_errorMessage!, textAlign: TextAlign.center),
                      const SizedBox(height: 24),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          onPressed: _restoreSession,
                          child: const Text('Retry'),
                        ),
                      ),
                      TextButton(
                        onPressed: _continueToLogin,
                        child: const Text('Go to Sign In'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    // No saved session exists.
    return const LoginScreen();
  }
}
