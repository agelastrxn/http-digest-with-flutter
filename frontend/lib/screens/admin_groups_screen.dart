import 'package:flutter/material.dart';

import 'admin_group_members_screen.dart';
import '../services/admin_service.dart';

class AdminGroupsScreen extends StatefulWidget {
  const AdminGroupsScreen({super.key});

  @override
  State<AdminGroupsScreen> createState() => _AdminGroupsScreenState();
}

class _AdminGroupsScreenState extends State<AdminGroupsScreen> {
  late final AdminService _adminService;

  late Future<Map<String, dynamic>> _groupsFuture;
  bool _isCreatingGroup = false;
  final Set<int> _updatingGroupIds = {};

  @override
  void initState() {
    super.initState();

    _adminService = AdminService();
    _groupsFuture = _adminService.getGroups();
  }

  void _reloadGroups() {
    setState(() {
      _groupsFuture = _adminService.getGroups();
    });
  }

  Future<void> _createGroup() async {
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (_) => const _CreateGroupDialog(),
    );

    if (result == null || !mounted) return;

    setState(() {
      _isCreatingGroup = true;
    });

    try {
      await _adminService.createGroup(
        name: result['name']!,
        description: result['description']!,
      );

      if (!mounted) return;

      _reloadGroups();

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Group created successfully.'),
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
          _isCreatingGroup = false;
        });
      }
    }
  }

  Future<void> _addGroupMember(Map<String, dynamic> group) async {
    final groupId = group['id'] as int;
    final groupName = group['name']?.toString() ?? 'Unknown';

    if (group['is_active'] != true) return;

    try {
      final usersData = await _adminService.getUsers(limit: 100);

      if (!mounted) return;

      final users = (usersData['users'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .where((user) => user['is_active'] == true)
          .toList();

      if (users.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No active users available.')),
        );
        return;
      }

      final selectedUserId = await showDialog<int>(
        context: context,
        builder: (_) => _AddGroupMemberDialog(users: users),
      );

      if (selectedUserId == null || !mounted) return;

      setState(() {
        _updatingGroupIds.add(groupId);
      });

      await _adminService.addGroupMember(
        groupId: groupId,
        userId: selectedUserId,
      );

      if (!mounted) return;

      _reloadGroups();

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('User successfully added to $groupName.'),
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
          _updatingGroupIds.remove(groupId);
        });
      }
    }
  }

  Future<void> _openGroupMembers(Map<String, dynamic> group) async {
    final groupId = group['id'] as int;
    final groupName = group['name']?.toString() ?? 'Unknown';

    await Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) =>
            AdminGroupMembersScreen(groupId: groupId, groupName: groupName),
      ),
    );

    if (!mounted) return;

    _reloadGroups();
  }

  Future<void> _toggleGroupStatus(Map<String, dynamic> group) async {
    final groupId = group['id'] as int;
    final groupName = group['name']?.toString() ?? 'Unknown';
    final isActive = group['is_active'] == true;
    final newStatus = !isActive;

    final action = newStatus ? 'enable' : 'disable';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: Text('${action.toUpperCase()} Group'),
          content: Text('Are you sure you want to $action "$groupName"?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: FilledButton.styleFrom(
                backgroundColor: newStatus ? Colors.green : Colors.red,
              ),
              child: Text(action.toUpperCase()),
            ),
          ],
        );
      },
    );

    if (confirmed != true || !mounted) return;

    setState(() {
      _updatingGroupIds.add(groupId);
    });

    try {
      await _adminService.updateGroupStatus(
        groupId: groupId,
        isActive: newStatus,
      );

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            newStatus
                ? '$groupName enabled successfully.'
                : '$groupName disabled successfully.',
          ),
          backgroundColor: Colors.green,
        ),
      );

      _reloadGroups();
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
          _updatingGroupIds.remove(groupId);
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
        title: const Text('Group Management'),
        actions: [
          IconButton(
            onPressed: _reloadGroups,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh groups',
          ),
        ],
      ),

      floatingActionButton: FloatingActionButton.extended(
        onPressed: _isCreatingGroup ? null : _createGroup,
        icon: _isCreatingGroup
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.add),
        label: const Text('Create Group'),
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _groupsFuture,
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
                      onPressed: _reloadGroups,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Try again'),
                    ),
                  ],
                ),
              ),
            );
          }

          final data = snapshot.data!;
          final groups = data['groups'] as List<dynamic>? ?? [];
          final total = data['total'] as int? ?? groups.length;

          return RefreshIndicator(
            onRefresh: () async {
              final future = _adminService.getGroups();

              setState(() {
                _groupsFuture = future;
              });

              await future;
            },
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'Total groups: $total',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 16),

                if (groups.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text('No groups found.')),
                  ),

                ...groups.map((item) {
                  final group = item as Map<String, dynamic>;

                  final groupId = group['id'];
                  final name = group['name']?.toString() ?? 'Unnamed group';
                  final description = group['description']?.toString() ?? '';
                  final memberCount = group['member_count'] as int? ?? 0;
                  final isActive = group['is_active'] == true;
                  final createdAt = group['created_at']?.toString() ?? '';

                  return Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: ListTile(
                      contentPadding: const EdgeInsets.all(16),
                      trailing: _updatingGroupIds.contains(groupId)
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  onPressed: () => _openGroupMembers(group),
                                  icon: const Icon(Icons.people_alt_outlined),
                                  tooltip: 'Manage members',
                                ),

                                IconButton(
                                  onPressed: isActive
                                      ? () => _addGroupMember(group)
                                      : null,
                                  icon: const Icon(
                                    Icons.person_add_alt_1,
                                    color: Colors.green,
                                  ),
                                  tooltip: 'Add member',
                                ),

                                IconButton(
                                  onPressed: () => _toggleGroupStatus(group),
                                  icon: Icon(
                                    isActive
                                        ? Icons.block
                                        : Icons.check_circle_outline,
                                    color: isActive ? Colors.red : Colors.green,
                                  ),
                                  tooltip: isActive
                                      ? 'Disable group'
                                      : 'Enable group',
                                ),
                              ],
                            ),
                      leading: CircleAvatar(
                        child: Icon(
                          Icons.groups_outlined,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      title: Text(
                        name,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      subtitle: Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (description.isNotEmpty) ...[
                              Text(description),
                              const SizedBox(height: 8),
                            ],
                            Text('Group ID: $groupId'),
                            Text('Members: $memberCount'),
                            if (createdAt.isNotEmpty)
                              Text('Created: $createdAt'),
                            const SizedBox(height: 8),
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

class _CreateGroupDialog extends StatefulWidget {
  const _CreateGroupDialog();

  @override
  State<_CreateGroupDialog> createState() => _CreateGroupDialogState();
}

class _CreateGroupDialogState extends State<_CreateGroupDialog> {
  final _formKey = GlobalKey<FormState>();

  late final TextEditingController _nameController;
  late final TextEditingController _descriptionController;

  @override
  void initState() {
    super.initState();

    _nameController = TextEditingController();
    _descriptionController = TextEditingController();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Create New Group'),
      content: SizedBox(
        width: 400,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Group Name',
                  hintText: 'Enter group name',
                  prefixIcon: Icon(Icons.groups),
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Group name is required.';
                  }

                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _descriptionController,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Description',
                  hintText: 'Enter group description (optional)',
                  prefixIcon: Icon(Icons.description_outlined),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: () {
            if (_formKey.currentState!.validate()) {
              Navigator.pop(context, {
                'name': _nameController.text.trim(),
                'description': _descriptionController.text.trim(),
              });
            }
          },
          icon: const Icon(Icons.add),
          label: const Text('Create'),
        ),
      ],
    );
  }
}

class _AddGroupMemberDialog extends StatefulWidget {
  final List<Map<String, dynamic>> users;

  const _AddGroupMemberDialog({required this.users});

  @override
  State<_AddGroupMemberDialog> createState() => _AddGroupMemberDialogState();
}

class _AddGroupMemberDialogState extends State<_AddGroupMemberDialog> {
  int? _selectedUserId;

  @override
  void initState() {
    super.initState();

    _selectedUserId = widget.users.first['id'] as int;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add Group Member'),
      content: SizedBox(
        width: 400,
        child: DropdownButtonFormField<int>(
          initialValue: _selectedUserId,
          decoration: const InputDecoration(
            labelText: 'Select User',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.person_outline),
          ),
          items: widget.users.map((user) {
            final id = user['id'] as int;
            final username = user['username']?.toString() ?? 'Unknown';

            return DropdownMenuItem<int>(
              value: id,
              child: Text('$username (ID: $id)'),
            );
          }).toList(),
          onChanged: (value) {
            setState(() {
              _selectedUserId = value;
            });
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _selectedUserId == null
              ? null
              : () {
                  Navigator.pop(context, _selectedUserId);
                },
          icon: const Icon(Icons.person_add),
          label: const Text('Add Member'),
        ),
      ],
    );
  }
}
