def user_has_role(user, role_name):
    return user.roles.filter(name=role_name).exists()


def has_permission(user, resource, action):
    for role in user.roles.all():
        perms = role.permissions or {}
        if action in perms.get(resource, []):
            return True
    return False