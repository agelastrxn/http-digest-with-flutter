import 'package:flutter/material.dart';

import '../services/admin_service.dart';

class AdminGroupMembersScreen extends StatefulWidget {
  final int groupId;
  final String groupName;

  const AdminGroupMembersScreen({
    super.key,
    required this.groupId,
    required this.groupName,
  });

  @override
  State<AdminGroupMembersScreen> createState() =>
      _AdminGroupMembersScreenState();
}

class _AdminGroupMembersScreenState extends State<AdminGroupMembersScreen> {
  late final AdminService _adminService;

  late Future<Map<String, dynamic>> _membersFuture;

  final Set<int> _removingUserIds = {};

  @override
  void initState() {
    super.initState();

    _adminService = AdminService();
    _membersFuture = _adminService.getGroupMembers(groupId: widget.groupId);
  }

  void _reloadMembers() {
    setState(() {
      _membersFuture = _adminService.getGroupMembers(groupId: widget.groupId);
    });
  }

  Future<void> _refreshMembers() async {
    final future = _adminService.getGroupMembers(groupId: widget.groupId);

    setState(() {
      _membersFuture = future;
    });

    await future;
  }

  Future<void> _removeMember(Map<String, dynamic> member) async {
    final userId = member['id'] as int;
    final username = member['username']?.toString() ?? 'Unknown';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Remove Group Member'),
          content: Text('Remove "$username" from "${widget.groupName}"?'),
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
              style: FilledButton.styleFrom(backgroundColor: Colors.red),
              child: const Text('Remove'),
            ),
          ],
        );
      },
    );

    if (confirmed != true || !mounted) return;

    setState(() {
      _removingUserIds.add(userId);
    });

    try {
      await _adminService.removeGroupMember(
        groupId: widget.groupId,
        userId: userId,
      );

      if (!mounted) return;

      _reloadMembers();

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$username removed from the group successfully.'),
          backgroundColor: Colors.green,
        ),
      );
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
          _removingUserIds.remove(userId);
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
        title: Text(widget.groupName),
        actions: [
          IconButton(
            onPressed: _reloadMembers,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh members',
          ),
        ],
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _membersFuture,
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
                      onPressed: _reloadMembers,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Try again'),
                    ),
                  ],
                ),
              ),
            );
          }

          final data = snapshot.data!;
          final members = data['members'] as List<dynamic>? ?? [];
          final total = data['total'] as int? ?? members.length;

          return RefreshIndicator(
            onRefresh: _refreshMembers,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'Group Members: $total',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 16),

                if (members.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(
                      child: Column(
                        children: [
                          Icon(
                            Icons.group_off_outlined,
                            size: 48,
                            color: Colors.grey,
                          ),
                          SizedBox(height: 12),
                          Text('This group has no members.'),
                        ],
                      ),
                    ),
                  ),

                ...members.map((item) {
                  final member = item as Map<String, dynamic>;

                  final userId = member['id'] as int;
                  final username = member['username']?.toString() ?? 'Unknown';
                  final role = member['role']?.toString() ?? 'user';
                  final isActive = member['is_active'] == true;

                  final isRemoving = _removingUserIds.contains(userId);

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
                        padding: const EdgeInsets.only(top: 6),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('User ID: $userId'),
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
                      trailing: isRemoving
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : IconButton(
                              onPressed: () {
                                _removeMember(member);
                              },
                              icon: const Icon(
                                Icons.person_remove_outlined,
                                color: Colors.red,
                              ),
                              tooltip: 'Remove member',
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
