import 'package:flutter/material.dart';

import 'screens/auth_gate.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  runApp(const DigestApplication());
}

class DigestApplication extends StatelessWidget {
  const DigestApplication({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Secure Access',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3157C8),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF3F5FA),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFFF8F9FC),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 18,
          ),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFFE1E5ED)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF3157C8), width: 1.5),
          ),
        ),
      ),
      home: const AuthGate(),
    );
  }
}
