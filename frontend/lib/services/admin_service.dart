import 'dart:convert';

import 'package:http/http.dart' as http;

import '../core/config/api_config.dart';
import 'session_storage_service.dart';

class AdminService {
  final http.Client _client;
  final SessionStorageService _storage;

  AdminService({http.Client? client, SessionStorageService? storage})
    : _client = client ?? http.Client(),
      _storage = storage ?? SessionStorageService();

  Future<Map<String, dynamic>> getUsers({
    int limit = 50,
    int offset = 0,
  }) async {
    if (limit < 1 || limit > 100 || offset < 0) {
      throw ArgumentError('Invalid pagination parameters.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint(ApiConfig.adminUsersEndpoint).replace(
      queryParameters: {'limit': limit.toString(), 'offset': offset.toString()},
    );

    final response = await _client.get(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error = decoded['error']?.toString() ?? 'Failed to load users.';

      throw Exception(error);
    }

    return decoded;
  }

  Future<void> disableUser(int userId) async {
    if (userId <= 0) {
      throw ArgumentError('Invalid user ID.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/users/$userId/disable');

    final response = await _client.post(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error = decoded['error']?.toString() ?? 'Failed to disable user.';

      throw Exception(error);
    }
  }

  Future<void> enableUser(int userId) async {
    if (userId <= 0) {
      throw ArgumentError('Invalid user ID.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/users/$userId/enable');

    final response = await _client.post(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error = decoded['error']?.toString() ?? 'Failed to enable user.';

      throw Exception(error);
    }
  }

  Future<void> changeUserRole(int userId, String newRole) async {
    if (userId <= 0) {
      throw ArgumentError('Invalid user ID.');
    }

    if (newRole != 'user' && newRole != 'admin') {
      throw ArgumentError('Invalid role.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/users/$userId/role');

    final response = await _client.post(
      uri,
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'role': newRole}),
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error =
          decoded['error']?.toString() ?? 'Failed to change user role.';

      throw Exception(error);
    }
  }

  Future<Map<String, dynamic>> getGroups({
    int limit = 50,
    int offset = 0,
  }) async {
    if (limit < 1 || limit > 100 || offset < 0) {
      throw ArgumentError('Invalid pagination parameters.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint(ApiConfig.adminGroupsEndpoint).replace(
      queryParameters: {'limit': limit.toString(), 'offset': offset.toString()},
    );

    final response = await _client.get(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error = decoded['error']?.toString() ?? 'Failed to load groups.';

      throw Exception(error);
    }

    return decoded;
  }

  Future<Map<String, dynamic>> createGroup({
    required String name,
    String description = '',
  }) async {
    if (name.trim().isEmpty) {
      throw ArgumentError('Group name cannot be empty.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint(ApiConfig.adminGroupsEndpoint);

    final response = await _client.post(
      uri,
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'name': name, 'description': description}),
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 201) {
      final error = decoded['error']?.toString() ?? 'Failed to create group.';

      throw Exception(error);
    }

    return decoded;
  }

  Future<void> addGroupMember({
    required int groupId,
    required int userId,
  }) async {
    if (groupId <= 0 || userId <= 0) {
      throw ArgumentError('Invalid group or user ID.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/groups/$groupId/members');

    final response = await _client.post(
      uri,
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'user_id': userId}),
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 201) {
      final error =
          decoded['error']?.toString() ?? 'Failed to add group member.';

      throw Exception(error);
    }
  }

  Future<void> removeGroupMember({
    required int groupId,
    required int userId,
  }) async {
    if (groupId <= 0 || userId <= 0) {
      throw ArgumentError('Invalid group or user ID.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint(
      '/api/admin/groups/$groupId/members/$userId',
    );

    final response = await _client.delete(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error =
          decoded['error']?.toString() ?? 'Failed to remove group member.';

      throw Exception(error);
    }
  }

  Future<Map<String, dynamic>> getGroupMembers({
    required int groupId,
    int limit = 100,
    int offset = 0,
  }) async {
    if (groupId <= 0 || limit < 1 || limit > 100 || offset < 0) {
      throw ArgumentError('Invalid request parameters.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/groups/$groupId/members')
        .replace(
          queryParameters: {
            'limit': limit.toString(),
            'offset': offset.toString(),
          },
        );

    final response = await _client.get(
      uri,
      headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'},
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error =
          decoded['error']?.toString() ?? 'Failed to load group members.';

      throw Exception(error);
    }

    return decoded;
  }

  Future<void> updateGroupStatus({
    required int groupId,
    required bool isActive,
  }) async {
    if (groupId <= 0) {
      throw ArgumentError('Invalid group ID.');
    }

    final token = await _storage.getToken();

    if (token == null || token.trim().isEmpty) {
      throw Exception('Authentication required.');
    }

    final uri = ApiConfig.endpoint('/api/admin/groups/$groupId/status');

    final response = await _client.patch(
      uri,
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'is_active': isActive}),
    );

    dynamic decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw Exception('Server returned invalid JSON.');
    }

    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected server response.');
    }

    if (response.statusCode != 200) {
      final error =
          decoded['error']?.toString() ?? 'Failed to update group status.';

      throw Exception(error);
    }
  }

  void dispose() {
    _client.close();
  }
}
