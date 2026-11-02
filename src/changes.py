def format_changes(before, after):
    changes = []
    for package in sorted(before.installed.keys() | after.installed.keys()):
        old = before.version_of(package)
        new = after.version_of(package)
        if old is None:
            changes.append(f"Install {package}=={new}")
        elif new is None:
            changes.append(f"Remove {package}=={old}")
        elif old != new:
            action = "Upgrade" if new > old else "Downgrade"
            changes.append(f"{action} {package}: {old} -> {new}")
    return changes
