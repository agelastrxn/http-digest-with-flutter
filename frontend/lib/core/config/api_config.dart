class ApiConfig {
  // Flask backend base URL.
  static const String baseUrl = 'http://127.0.0.1:5000';

  // Authentication endpoints.
  static const String registerEndpoint = '/api/auth/register';
  static const String digestLoginEndpoint = '/api/auth/digest';
  static const String backupLoginEndpoint = '/api/auth/backup-login';
  static const String logoutEndpoint = '/api/auth/logout';
  static const String recoverEndpoint = '/api/auth/recover';
  static const String backupCodesEndpoint = '/api/auth/backup-codes';

  // User endpoints.
  static const String profileEndpoint = '/api/auth/me';
  static const String changePasswordEndpoint = '/api/auth/change-password';

  // Admin endpoints.
  static const String adminUsersEndpoint = '/api/admin/users';
  static const String adminGroupsEndpoint = '/api/admin/groups';

  // Build a complete API URI.
  static Uri endpoint(String path) {
    return Uri.parse('$baseUrl$path');
  }
}
