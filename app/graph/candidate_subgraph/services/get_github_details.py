from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from app.schemas import JDRequirements
from .get_github_text import build_github_text


logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=10.0,
    write=5.0,
    pool=5.0,
)

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not configured")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "CandidateScreeningPlatform",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
}


class GitHubClient:

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=TIMEOUT,
            headers=HEADERS,
            follow_redirects=False,
        )

    async def close(self):
        await self.client.aclose()

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 2,
    ) -> httpx.Response | None:

        for attempt in range(retries + 1):

            try:
                response = await self.client.get(
                    url,
                    params=params,
                    headers=headers,
                )

                # Rate limited
                if response.status_code in (403, 429):

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    if retry_after:
                        wait = min(float(retry_after), 10)
                    else:
                        wait = min(2 ** attempt, 10)

                    if attempt < retries:
                        await asyncio.sleep(wait)
                        continue

                    logger.warning(
                        "GitHub rate limit reached: %s",
                        url,
                    )

                    return None

                # Temporary GitHub/server failure
                if response.status_code >= 500:

                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    logger.error(
                        "GitHub server error %s: %s",
                        response.status_code,
                        url,
                    )

                    return None

                return response

            except httpx.TimeoutException:

                logger.warning(
                    "GitHub request timed out: %s",
                    url,
                )

                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

                return None

            except httpx.RequestError as exc:

                logger.warning(
                    "GitHub request failed: %s - %s",
                    url,
                    exc,
                )

                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

                return None

            except Exception:

                logger.exception(
                    "Unexpected GitHub error: %s",
                    url,
                )

                return None

        return None

    # ---------------------------------------------------------
    # 1. Validate GitHub URL
    # ---------------------------------------------------------

    @staticmethod
    def validate_github_url(
        url: str | None,
    ) -> str | None:

        if not url:
            return None

        try:
            url = url.strip()

            if not url:
                return None

            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            parsed = urlparse(url)

            if parsed.netloc.lower() not in {
                "github.com",
                "www.github.com",
            }:
                return None

            parts = [
                part
                for part in parsed.path.split("/")
                if part
            ]

            # Only accept profile URLs:
            # github.com/username
            if len(parts) != 1:
                return None

            username = parts[0]

            if username.lower() in {
                "login",
                "signup",
                "settings",
                "notifications",
            }:
                return None

            return username

        except Exception:

            logger.exception(
                "Failed to validate GitHub URL"
            )

            return None

    # ---------------------------------------------------------
    # 2. Get profile
    # ---------------------------------------------------------

    async def get_github_profile(
        self,
        username: str | None,
    ) -> dict[str, Any] | None:

        if not username:
            return None

        url = f"{GITHUB_API}/users/{username}"

        response = await self._get(url)

        if response is None:
            return None

        if response.status_code == 404:
            return None

        if response.status_code != 200:

            logger.warning(
                "Unexpected GitHub profile status: %s",
                response.status_code,
            )

            return None

        try:

            data = response.json()

            return {
                "username": data.get("login"),
                "name": data.get("name"),
                "bio": data.get("bio"),
                "followers": data.get("followers", 0),
                "public_repos": data.get("public_repos", 0),
                "profile_url": data.get("html_url"),
            }

        except (ValueError, TypeError):

            logger.exception(
                "Invalid GitHub profile response for %s",
                username,
            )

            return None

    # ---------------------------------------------------------
    # 3. Get repositories
    # ---------------------------------------------------------

    async def get_github_repositories(
        self,
        username: str | None,
    ) -> list[dict[str, Any]]:

        if not username:
            return []

        url = f"{GITHUB_API}/users/{username}/repos"

        params = {
            "type": "owner",
            "sort": "updated",
            "per_page": 100,
        }

        response = await self._get(
            url,
            params=params,
        )

        if response is None:
            return []

        if response.status_code == 404:
            return []

        if response.status_code != 200:

            logger.warning(
                "Unexpected repository status: %s",
                response.status_code,
            )

            return []

        try:

            repos = response.json()

            if not isinstance(repos, list):
                return []

            return [
                {
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "description": repo.get("description"),
                    "stars": repo.get(
                        "stargazers_count",
                        0,
                    ),
                    "language": repo.get("language"),
                    "url": repo.get("html_url"),
                    "updated_at": repo.get("updated_at"),
                }
                for repo in repos
            ]

        except (ValueError, TypeError):

            logger.exception(
                "Invalid repository response for %s",
                username,
            )

            return []

    # ---------------------------------------------------------
    # 4. Filter repositories using JD requirements
    # ---------------------------------------------------------

    def filter_repositories(
        self,
        repositories: list[dict[str, Any]],
        jd_requirements: JDRequirements,
    ) -> list[dict[str, Any]]:

        skills = (
            jd_requirements.required_skills
            + jd_requirements.preferred_skills
            + jd_requirements.required_languages
            + jd_requirements.keywords
        )

        if not skills:
            return repositories

        skills = [
            skill.lower().strip()
            for skill in skills
            if skill
        ]

        filtered_repositories = []

        for repo in repositories:

            searchable_text = " ".join(
                str(repo.get(field) or "")
                for field in (
                    "name",
                    "description",
                    "language",
                )
            ).lower()

            if any(
                skill in searchable_text
                for skill in skills
            ):
                filtered_repositories.append(repo)

        logger.info(
            "Filtered repositories: %s -> %s",
            len(repositories),
            len(filtered_repositories),
        )

        return filtered_repositories

    # ---------------------------------------------------------
    # 5. Get repository details
    # ---------------------------------------------------------

    async def get_repository_details(
        self,
        owner: str | None,
        repo: str | None,
    ) -> dict[str, Any] | None:

        if not owner or not repo:
            return None

        url = f"{GITHUB_API}/repos/{owner}/{repo}"

        response = await self._get(url)

        if response is None:
            return None

        if response.status_code == 404:
            return None

        if response.status_code != 200:

            logger.warning(
                "Unexpected repository detail status: %s",
                response.status_code,
            )

            return None

        try:

            data = response.json()

            # GitHub repository response contains topics.
            topics = data.get("topics") or []

            # Get languages separately.
            languages_url = data.get("languages_url")

            languages = []

            if languages_url:

                languages_response = await self._get(
                    languages_url
                )

                if (
                    languages_response
                    and languages_response.status_code == 200
                ):

                    try:

                        languages_data = (
                            languages_response.json()
                        )

                        if isinstance(
                            languages_data,
                            dict,
                        ):
                            languages = list(
                                languages_data.keys()
                            )

                    except (ValueError, TypeError):

                        logger.warning(
                            "Invalid languages response for %s/%s",
                            owner,
                            repo,
                        )

            return {
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "stars": data.get(
                    "stargazers_count",
                    0,
                ),
                "topics": topics,
                "languages": languages,
                "url": data.get("html_url"),
            }

        except (ValueError, TypeError):

            logger.exception(
                "Invalid repository response for %s/%s",
                owner,
                repo,
            )

            return None

    # ---------------------------------------------------------
    # 6. Get README
    # ---------------------------------------------------------

    async def get_repository_readme(
        self,
        owner: str | None,
        repo: str | None,
    ) -> str | None:

        if not owner or not repo:
            return None

        url = f"{GITHUB_API}/repos/{owner}/{repo}/readme"

        headers = {
            **HEADERS,
            "Accept": "application/vnd.github.raw+json",
        }

        response = await self._get(
            url,
            headers=headers,
        )

        if response is None:
            return None

        if response.status_code == 404:
            return None

        if response.status_code != 200:

            logger.warning(
                "Unexpected README status for %s/%s: %s",
                owner,
                repo,
                response.status_code,
            )

            return None

        return response.text


# =============================================================
# GitHub Analysis
# =============================================================

async def analyze_github(
    github_url: str | None,
    jd_requirements: JDRequirements,
):
    client = GitHubClient()

    try:

        # 1. Validate GitHub URL
        username = client.validate_github_url(
            github_url
        )

        if not username:
            return None

        # 2. Get profile
        profile = await client.get_github_profile(
            username
        )

        if not profile:
            return None

        # 3. Get repositories
        repositories = await client.get_github_repositories(
            username
        )

        # 4. Filter repositories using JD requirements
        filtered_repositories = client.filter_repositories(
            repositories,
            jd_requirements,
        )

        repo_data = []

        # 5. Only deeply inspect relevant repositories
        for repo in filtered_repositories:

            full_name = repo.get("full_name")

            if not full_name:
                continue

            owner, repo_name = full_name.split(
                "/",
                1,
            )

            # 6. Get repository details
            details = await client.get_repository_details(
                owner,
                repo_name,
            )

            # 7. Get README
            readme = await client.get_repository_readme(
                owner,
                repo_name,
            )

            repo_data.append({
                "metadata": repo,
                "details": details,
                "readme": readme,
            })

        # 8. Store complete GitHub data
        github_data = {
            "profile": profile,
            "repositories": repo_data,
        }

        # 9. Create compact text for LLM
        github_text = build_github_text(
            repo_data
        )

        return {
            "github_data": github_data,
            "github_text": github_text,
        }

    finally:

        await client.close()