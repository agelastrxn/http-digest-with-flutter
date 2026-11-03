import 'package:flutter/material.dart';

import '../services/admin_service.dart';

class AdminUsersScreen extends StatefulWidget {
  const AdminUsersScreen({super.key});

  @override
  State<AdminUsersScreen> createState() => _AdminUsersScreenState();
}

class _AdminUsersScreenState extends State<AdminUsersScreen> {
  late final AdminService _adminService;

  late Future<Map<String, dynamic>> _usersFuture;

  final Set<int> _updatingUserIds = {};

  @override
  void initState() {
    super.initState();

    _adminService = AdminService();
    _usersFuture = _adminService.getUsers();
  }

  void _reloadUsers() {
    setState(() {
      _usersFuture = _adminService.getUsers();
    });
  }

  Future<void> _disableUser(Map<String, dynamic> user) async {
    final userId = user['id'] as int;
    final username = user['username']?.toString() ?? 'Unknown';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Disable user'),
          content: Text('Are you sure you want to disable "$username"?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              style: FilledButton.styleFrom(backgroundColor: Colors.red),
              child: const Text('Disable'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    setState(() {
      _updatingUserIds.add(userId);
    });

    try {
      await _adminService.disableUser(userId);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$username has been disabled successfully.'),
          backgroundColor: Colors.green,
        ),
      );

      _reloadUsers();
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _updatingUserIds.remove(userId);
        });
      }
    }
  }

  Future<void> _enableUser(Map<String, dynamic> user) async {
    final userId = user['id'] as int;
    final username = user['username']?.toString() ?? 'Unknown';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Enable user'),
          content: Text('Are you sure you want to enable "$username"?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Enable'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    setState(() {
      _updatingUserIds.add(userId);
    });

    try {
      await _adminService.enableUser(userId);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$username has been enabled successfully.'),
          backgroundColor: Colors.green,
        ),
      );

      _reloadUsers();
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _updatingUserIds.remove(userId);
        });
      }
    }
  }

  Future<void> _changeUserRole(
    Map<String, dynamic> user,
    String newRole,
  ) async {
    final userId = user['id'] as int;
    final username = user['username']?.toString() ?? 'Unknown';
    final currentRole = user['role']?.toString() ?? 'user';

    if (currentRole == newRole) return;

    final roleLabel = newRole == 'admin' ? 'Administrator' : 'Regular User';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Change User Role'),
          content: Text('Change $username\'s role to $roleLabel?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Confirm'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    setState(() {
      _updatingUserIds.add(userId);
    });

    try {
      await _adminService.changeUserRole(userId, newRole);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$username\'s role updated successfully.'),
          backgroundColor: Colors.green,
        ),
      );

      _reloadUsers();
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _updatingUserIds.remove(userId);
        });
      }
    }
  }

  @override
  void dispose() {
    _adminService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('User Management'),
        actions: [
          IconButton(
            onPressed: _reloadUsers,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh users',
          ),
        ],
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _usersFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.error_outline,
                      color: Colors.red,
                      size: 48,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      snapshot.error.toString(),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: _reloadUsers,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Try again'),
                    ),
                  ],
                ),
              ),
            );
          }

          final data = snapshot.data!;
          final users = data['users'] as List<dynamic>? ?? [];
          final total = data['total'] as int? ?? users.length;

          return RefreshIndicator(
            onRefresh: () async {
              _reloadUsers();
              await _usersFuture;
            },
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'Registered users: $total',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 16),

                if (users.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text('No users found.')),
                  ),

                ...users.map((item) {
                  final user = item as Map<String, dynamic>;

                  final userId = user['id'] as int;
                  final username = user['username']?.toString() ?? 'Unknown';
                  final role = user['role']?.toString() ?? 'user';
                  final isActive = user['is_active'] == true;
                  final isDisabling = _updatingUserIds.contains(userId);

                  return Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: ListTile(
                      contentPadding: const EdgeInsets.all(12),
                      leading: CircleAvatar(
                        child: Text(
                          username.isNotEmpty ? username[0].toUpperCase() : '?',
                        ),
                      ),
                      title: Text(
                        username,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      subtitle: Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('ID: $userId'),
                            Text('Role: $role'),
                            const SizedBox(height: 6),
                            Row(
                              children: [
                                Icon(
                                  Icons.circle,
                                  size: 10,
                                  color: isActive ? Colors.green : Colors.red,
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  isActive ? 'Active' : 'Disabled',
                                  style: TextStyle(
                                    color: isActive ? Colors.green : Colors.red,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          PopupMenuButton<String>(
                            enabled: !_updatingUserIds.contains(userId),
                            tooltip: 'Change user role',
                            onSelected: (newRole) {
                              _changeUserRole(user, newRole);
                            },
                            itemBuilder: (context) => [
                              if (role == 'user')
                                const PopupMenuItem(
                                  value: 'admin',
                                  child: Text('Make Administrator'),
                                ),
                              if (role == 'admin')
                                const PopupMenuItem(
                                  value: 'user',
                                  child: Text('Make Regular User'),
                                ),
                            ],
                            icon: const Icon(Icons.manage_accounts_outlined),
                          ),

                          if (_updatingUserIds.contains(userId))
                            const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          else if (isActive)
                            IconButton(
                              onPressed: () => _disableUser(user),
                              icon: const Icon(Icons.block, color: Colors.red),
                              tooltip: 'Disable user',
                            )
                          else
                            IconButton(
                              onPressed: () => _enableUser(user),
                              icon: const Icon(
                                Icons.lock_open,
                                color: Colors.green,
                              ),
                              tooltip: 'Enable user',
                            ),
                        ],
                      ),
                    ),
                  );
                }),
              ],
            ),
          );
        },
      ),
    );
  }
}
