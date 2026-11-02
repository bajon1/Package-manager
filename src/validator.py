from collections.abc import Iterable

from .model import Repository, Requirement, State, alternative_to_str


def requirement_satisfied(state: State, requirement: Requirement) -> bool:
    version = state.version_of(requirement.package)
    return version is not None and requirement.matches(version)


def validate_state(
    repository: Repository, state: State, requests: Iterable[Requirement] = (),
) -> list[str]:
    errors = []
    for package, version in sorted(state.installed.items()):
        installed = next(
            (pv for pv in repository.versions(package) if pv.version == version),
            None,
        )
        if installed is None:
            errors.append(f"{package}=={version}: version does not exist in the repository")
            continue

        for alternative in installed.requires:
            if not any(requirement_satisfied(state, req) for req in alternative):
                errors.append(
                    f"{installed}: unsatisfied requirement '{alternative_to_str(alternative)}'")

        for conflict in installed.conflicts:
            if requirement_satisfied(state, conflict):
                errors.append(
                    f"{installed}: conflict '{conflict}' matches installed "
                    f"{conflict.package}=={state.version_of(conflict.package)}")

    for request in requests:
        if not requirement_satisfied(state, request):
            errors.append(f"Unsatisfied request '{request}'")

    return errors
