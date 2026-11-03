import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/auth_service.dart';

class BackupCodesScreen extends StatefulWidget {
  const BackupCodesScreen({super.key});

  @override
  State<BackupCodesScreen> createState() => _BackupCodesScreenState();
}

class _BackupCodesScreenState extends State<BackupCodesScreen> {
  final _passwordController = TextEditingController();
  final AuthService _authService = AuthService();

  List<String>? _backupCodes;

  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _errorMessage;

  Future<void> _generateCodes() async {
    if (_passwordController.text.isEmpty) {
      setState(() {
        _errorMessage = 'Current password is required.';
      });
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          icon: const Icon(
            Icons.warning_amber_rounded,
            color: Colors.orange,
            size: 40,
          ),
          title: const Text('Generate Backup Codes?'),
          content: const Text(
            'Generating new codes will revoke all previously '
            'unused backup codes. Continue?',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(dialogContext, false);
              },
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(dialogContext, true);
              },
              child: const Text('Generate'),
            ),
          ],
        );
      },
    );

    if (!mounted || confirmed != true) return;

    FocusScope.of(context).unfocus();

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final codes = await _authService.generateBackupCodes(
        currentPassword: _passwordController.text,
      );

      if (!mounted) return;

      setState(() {
        _backupCodes = codes;
        _isLoading = false;
      });

      _passwordController.clear();

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Backup codes generated successfully.'),
          backgroundColor: Colors.green,
        ),
      );
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _errorMessage = error.toString().replaceFirst('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  Future<void> _copyCode(String code) async {
    await Clipboard.setData(ClipboardData(text: code));

    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Backup code copied to clipboard.'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  Future<void> _copyAllCodes() async {
    final codes = _backupCodes;

    if (codes == null || codes.isEmpty) return;

    await Clipboard.setData(ClipboardData(text: codes.join('\n')));

    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('All backup codes copied successfully.'),
        backgroundColor: Colors.green,
      ),
    );
  }

  Widget _buildGenerationForm(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(Icons.key_outlined, size: 58, color: Colors.blue),
        const SizedBox(height: 18),
        Text(
          'Generate Backup Codes',
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Backup codes allow you to access your account '
          'when you cannot use your regular password.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: Colors.grey.shade600,
          ),
        ),
        const SizedBox(height: 28),
        TextFormField(
          controller: _passwordController,
          enabled: !_isLoading,
          obscureText: _obscurePassword,
          decoration: InputDecoration(
            labelText: 'Current Password',
            prefixIcon: const Icon(Icons.lock_outline),
            border: const OutlineInputBorder(),
            suffixIcon: IconButton(
              onPressed: () {
                setState(() {
                  _obscurePassword = !_obscurePassword;
                });
              },
              icon: Icon(
                _obscurePassword
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
              ),
            ),
          ),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.orange.shade50,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.orange.shade200),
          ),
          child: const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.warning_amber_rounded, color: Colors.orange),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Generating new codes invalidates all '
                  'previously unused backup codes. '
                  'Each code can only be used once.',
                ),
              ),
            ],
          ),
        ),
        if (_errorMessage != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(),
        ],
        const SizedBox(height: 24),
        SizedBox(
          height: 52,
          child: FilledButton(
            onPressed: _isLoading ? null : _generateCodes,
            child: _isLoading
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Generate 10 Backup Codes'),
          ),
        ),
      ],
    );
  }

  Widget _buildCodesList(ThemeData theme) {
    final codes = _backupCodes!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(Icons.verified_outlined, size: 58, color: Colors.green),
        const SizedBox(height: 16),
        Text(
          'Backup Codes Ready',
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Save these codes in a secure place. '
          'They will not be shown again after leaving this screen.',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: Colors.grey.shade600,
          ),
        ),
        const SizedBox(height: 24),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.orange.shade50,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.orange.shade200),
          ),
          child: const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.security, color: Colors.orange),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Each backup code is single-use. '
                  'Keep these codes private and never share them.',
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        ...List.generate(codes.length, (index) {
          return Card(
            margin: const EdgeInsets.only(bottom: 10),
            child: ListTile(
              leading: CircleAvatar(radius: 16, child: Text('${index + 1}')),
              title: SelectableText(
                codes[index],
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
              trailing: IconButton(
                tooltip: 'Copy code',
                onPressed: () => _copyCode(codes[index]),
                icon: const Icon(Icons.copy_outlined),
              ),
            ),
          );
        }),
        const SizedBox(height: 16),
        SizedBox(
          height: 50,
          child: FilledButton.icon(
            onPressed: _copyAllCodes,
            icon: const Icon(Icons.copy_all_outlined),
            label: const Text('Copy All Codes'),
          ),
        ),
      ],
    );
  }

  Widget _buildErrorMessage() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.red.shade200),
      ),
      child: Text(_errorMessage!, style: TextStyle(color: Colors.red.shade800)),
    );
  }

  @override
  void dispose() {
    _passwordController.dispose();
    _authService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Backup Codes')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Card(
                color: Colors.white,
                elevation: 2,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: _backupCodes == null
                      ? _buildGenerationForm(theme)
                      : _buildCodesList(theme),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
