from langchain_core.prompts import ChatPromptTemplate


github_eval_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are evaluating a candidate's GitHub profile for a job.

Evaluate how strongly the candidate's GitHub projects demonstrate
the skills and experience required by the job description.

Consider:
- Relevance of projects to required skills
- Technologies and languages demonstrated
- Depth and complexity of projects
- Evidence from project descriptions and README content
- Alignment with the job's requirements

Do not assume skills that are not supported by the provided GitHub evidence.

Return a score from 0 to 100 and a concise reasoning.
"""
    ),
    (
        "human",
        """
Job Requirements:
{jd_requirements}

GitHub Projects:
{github_text}
"""
    ),
])