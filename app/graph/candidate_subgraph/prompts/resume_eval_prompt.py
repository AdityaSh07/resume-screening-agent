from langchain_core.prompts import ChatPromptTemplate

resume_eval_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are an expert technical recruiter.

Evaluate a candidate's resume against the job requirements.

Give an overall match score from 0 to 100.

Consider:
- Required technical skills
- Relevant experience
- Education
- Projects
- Seniority/experience level
- Alignment with the job requirements

Do not give a high score merely because the resume contains similar keywords.
Evaluate actual relevance and evidence.

Return a score between 0 and 100.
""",
    ),
    (
        "human",
        """
Job Requirements:
{jd_requirements}

Candidate Resume:
{resume_data}
""",
    ),
])
