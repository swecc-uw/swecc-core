# Declare consumers here
from . import consumer as mq_consumer
import json
import logging

logger = logging.getLogger(__name__)
from ..aws.s3 import S3Client
from ..llm.gemini import Gemini
from .producers import finish_review


RESUME_PROMPT = """
You are an expert software engineering recruiter and hiring manager who has screened thousands of resumes at top tech companies. Review the following resume carefully and provide feedback that is:

### Review Criteria
1. Actionable - Give extremely specific, implementable suggestions. Rewrite weak bullets into strong XYZ format where possible.
2. Metrics-Driven - Every bullet should ideally include a measurable outcome (numbers, percentages, time saved, performance improvements, scale, adoption, efficiency). Identify missing metrics and suggest concrete ways to quantify impact.
3. XYZ Format Focus - Each bullet should follow the "Accomplished X by doing Y, resulting in Z" structure. Highlight bullets that do not follow this format and provide rewritten examples.
4. Prioritized - Call out the highest-impact improvements first (e.g., missing metrics, weak XYZ statements, unclear technical impact).
5. Tailored to SWE Roles - Emphasize technical depth, problem-solving, debugging, scalability, and system design. Remove generic teamwork or soft-skill fluff.
6. Balanced - Point out both strengths (well-written, measurable, technically strong bullets) and weaknesses (vague, metric-less, non-technical bullets).
7. Concise & Structured - Use bullet points grouped by section (Experience, Projects, Skills, Education).

### General Things to Look For
- Clarity & Readability: Clean, consistent formatting that is scannable in <30 seconds.
- Metrics & Impact: Highlight where measurable outcomes exist and suggest ways to add them. Every bullet should quantify the contribution if possible.
- XYZ Format: Assess every bullet. Rewrite unclear or incomplete bullets into clear "X by Y, resulting in Z" statements.
- Technical Skills: Are languages, frameworks, and tools integrated into experiences rather than just listed? Emphasize coding, architecture, algorithms, and system-level work.
- Action Verbs: Start bullets with strong verbs like “Designed,” “Implemented,” “Optimized,” “Built,” “Automated.”
- Relevance: Focus on technical problem-solving, design, scalability, and debugging. Remove or minimize generic collaboration or leadership fluff unless tied to technical outcomes.
- Project Descriptions: Clearly outline the problem, solution, and measurable impact.
- Consistency & ATS: Uniform tense, punctuation, formatting, and inclusion of SWE-relevant keywords.
- Summary Sections: Avoid or remove them for SWE roles; they rarely add value.

Include only your feedback and no extra commentary. Focus on **rewriting bullets to maximize measurable impact and adherence to the XYZ format**, along with providing overall feedback. Be critical and direct.
"""


@mq_consumer(
    queue="ai.to-review-queue", exchange="swecc-ai-exchange", routing_key="to-review"
)
async def consume_to_review_message(body, properties):
    message_str = body.decode("utf-8")
    message: dict = json.loads(message_str)

    logger.info(f"Received message: {message}")

    file_key = message["key"]
    s3_client = S3Client()
    file_content = s3_client.retrieve_object(file_key)

    gemini_client = Gemini()
    response = await gemini_client.prompt_file(
        bytes=file_content, prompt=RESUME_PROMPT, mime_type="application/pdf"
    )

    logger.info(f"Gemini response: {response}")

    await finish_review({"feedback": response, "key": file_key})
