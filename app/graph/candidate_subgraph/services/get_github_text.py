from typing import Any

def build_github_text(
    repositories: list[dict[str, Any]],
) -> str:

    github_text = []

    for repo in repositories:
        details = repo.get("details") or {}

        name = details.get("name", "Unknown")
        languages = details.get("languages", [])
        description = details.get("description") or ""
        readme = repo.get("readme") or ""

        readme = readme[:500]

        github_text.append(
            f"""
Repository: {name}
Languages: {", ".join(languages)}
Description: {description}
README:
{readme}
""".strip()
        )

    return "\n\n".join(github_text)