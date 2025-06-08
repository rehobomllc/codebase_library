'''
Agent for processing raw crawled scholarship data into structured format.
'''
import json
from agents import Agent, Tool, tool, RunConfig, ItemHelpers # Make sure ItemHelpers is available if used by Runner internally
from arcadepy import AsyncArcade

async def create_processing_agent(arcade_client: AsyncArcade, get_tools_func=None):
    '''
    Creates an agent specialized in processing raw web crawl data to extract
    structured scholarship information.
    '''
    # The get_tools_func is not used for now, as this agent primarily relies on its
    # LLM capabilities to parse text provided in the prompt.
    # If it needed specific Arcade tools (e.g., to fetch external data for validation),
    # those would be configured here.

    system_prompt = """
You are an AI assistant specialized in processing raw web crawl data to extract structured scholarship information.
Your goal is to identify and structure distinct scholarship opportunities from the provided text.
For each scholarship, extract the following details if available:
- name: The official name of the scholarship.
- description: A brief summary of the scholarship.
- eligibility: Key eligibility criteria (be concise).
- deadline: Application deadline (e.g., "YYYY-MM-DD", "Varies", "Monthly").
- amount: Award amount (e.g., "$5,000", "Up to $10,000", "Varies").
- url: The direct URL to the scholarship page or more information.

Aim to find at least 25 high-quality, distinct scholarship opportunities if the data supports it.
If the raw data is provided as a list of items (e.g., page contents), process each relevant item.
Focus on accuracy and completeness of the extracted information.

Respond with ONLY a valid JSON list of scholarship objects. Do not include any explanatory text before or after the JSON list.
Example of a scholarship object in the list:
{
  "name": "Future Leaders Grant",
  "description": "A grant for aspiring leaders in STEM fields.",
  "eligibility": "Enrolled in a STEM program, GPA 3.5+",
  "deadline": "2024-12-31",
  "amount": "$5,000",
  "url": "https://example.com/future-leaders"
}

If you cannot find a specific piece of information for a scholarship, you can use "N/A" or omit the field if appropriate for that scholarship.
Ensure your entire response is just the JSON list, starting with '[' and ending with ']'.
"""
    return Agent(
        name="ScholarshipProcessingAgent",
        instructions=system_prompt,
        model="gpt-4.1",
        tools=[]
    )
