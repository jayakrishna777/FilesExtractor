from crewai import Agent, Task, Crew , LLM
import os
from extracttool import FeedGuideNavigator
import json
from dotenv import load_dotenv
load_dotenv()

openai_llm=LLM(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

data_extractor_agent = Agent(
    role="DataExtractorAgent",
    goal="Extract data from websites as per the provided feed guide and save the files locally.",
    backstory="An agent that uses a feed guide to navigate websites and download files.",
    tools=[FeedGuideNavigator()],
    llm=openai_llm
)

philly_feed = {
  "feed_name": "PhillyFed_MFG",
  "steps": [
    {"action": "goto", "url": "https://www.philadelphiafed.org"},
    {"action": "click", "text": "Surveys & Data"},
    {"action": "click", "text": "Manufacturing Business Outlook Survey"},
    {"action": "click", "text": "Download the full history"},
    {"action": "download", "text": "bos_history.xls", "save_as": "bos_history.xls"}
  ]
}

task=Task(
    description="Call the feed_guide_navigator tool with the provided feed_guide to download the files.",
    expected_output="A summary of the download result and the path to the downloaded file(s).",  
    agent=data_extractor_agent
)



crew = Crew(agents=[data_extractor_agent], tasks=[task],verbose=True)
result= crew.kickoff(inputs=philly_feed)
print("Final Result:", result)