"""
Agent responsible for generating metadata entries after each research session.

The MetaTagAgent captures key information about the user query and generated response,
including nuance, sentiment, reflection, and content. This metadata is stored and
updated to a vector store for future reference and retrieval.
"""
from datetime import datetime
import json
import os
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from .baseclass import ResearchAgent, ResearchRunner
from ..llm_config import LLMConfig, model_supports_structured_output
from .utils.parse_output import create_type_parser
from .vector_store_updater import VectorStoreUpdater


class MetaTagEntry(BaseModel):
    """Metadata entry for a research session"""
    query: str = Field(description="The original user query")
    timestamp: str = Field(description="Timestamp when the entry was created")
    summary: str = Field(description="A comprehensive summary of the research findings")
    key_entities: List[str] = Field(description="Important entities mentioned in the report")
    user_intent: str = Field(description="Analysis of what the user was trying to accomplish")
    sentiment: str = Field(description="Overall sentiment of the content and context")
    topics: List[str] = Field(description="Main topics covered in the research")
    content_reflection: str = Field(description="Reflection on the content and its implications")
    most_relevant_facilities: List[str] = Field(description="List of most relevant facilities mentioned in the report")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "What's the best alcohol treatment facility in West LA?",
                "timestamp": "2023-07-21T14:32:15",
                "summary": "Research identified five alcohol treatment facilities in West LA with varying services, insurance coverage, and accreditation",
                "key_entities": ["Harmony Treatment Center", "West LA Recovery", "Serenity Hills", "Pacific Wellness"],
                "user_intent": "User seeking to identify and compare alcohol treatment options with a focus on quality and accessibility",
                "sentiment": "Information-seeking, decision-oriented with urgency",
                "topics": ["alcohol treatment", "rehabilitation centers", "West Los Angeles", "insurance coverage", "outpatient services"],
                "content_reflection": "The research provides comparative data but emphasizes the need for personal evaluation of facility fit",
                "most_relevant_facilities": ["Harmony Treatment Center", "Pacific Wellness"]
            }
        }


INSTRUCTIONS = f"""
You are a metadata specialist who analyzes research reports and user queries to create rich metadata entries.
Today's date is {datetime.now().strftime("%Y-%m-%d")}.

Your task is to generate a comprehensive metadata entry based on:
1. The original user query
2. The final research report content

Create metadata that will be useful for future retrieval, containing:
- A concise but complete summary of the research findings
- Key entities mentioned (especially facility names)
- Analysis of user intent and goals
- Sentiment of both query and content
- Main topics covered
- A brief reflection on the content and its context
- List of the most relevant facilities mentioned in the report

This metadata will be stored in a vector database to enhance future research queries on similar topics.
Your analysis must be objective, thorough, and capture the nuance of both the query and response.

Only output JSON and follow the JSON schema below. Do not output anything else. I will be parsing this with Pydantic so output valid JSON only:
{MetaTagEntry.model_json_schema()}
"""


class MetaTagAgent:
    """
    Agent that generates metadata entries and updates the vector store
    after each research session.
    """
    
    def __init__(self, config: LLMConfig, vector_store_id: Optional[str] = None, metadata_file_path: Optional[str] = None):
        """
        Initialize the MetaTagAgent.
        
        Args:
            config: LLM configuration
            vector_store_id: ID of the vector store to update (if None, will only save to file)
            metadata_file_path: Path to the metadata JSON file (defaults to 'metadata.json' in current directory)
        """
        self.config = config
        self.vector_store_id = vector_store_id
        self.metadata_file_path = metadata_file_path or os.path.join(os.getcwd(), 'metadata.json')
        self.agent = self._init_agent()
        
    def _init_agent(self) -> ResearchAgent:
        """Initialize the underlying agent with instructions."""
        selected_model = self.config.fast_model
        
        return ResearchAgent(
            name="MetaTagAgent",
            instructions=INSTRUCTIONS,
            model=selected_model,
            output_type=MetaTagEntry if model_supports_structured_output(selected_model) else None,
            output_parser=create_type_parser(MetaTagEntry) if not model_supports_structured_output(selected_model) else None
        )
    
    async def generate_metadata(self, query: str, report_content: str) -> MetaTagEntry:
        """
        Generate metadata for the research session.
        
        Args:
            query: The original user query
            report_content: The full content of the research report
            
        Returns:
            MetaTagEntry object containing the metadata
        """
        user_message = f"""
        QUERY:
        {query}
        
        REPORT CONTENT:
        {report_content}
        """
        
        result = await ResearchRunner.run(
            self.agent,
            user_message,
        )
        
        metadata = result.final_output_as(MetaTagEntry)
        return metadata
    
    async def process_and_save(self, query: str, report_content: str) -> Dict[str, Any]:
        """
        Process a research session, generate metadata, and save to file.
        Optionally updates the vector store if vector_store_id is provided.
        
        Args:
            query: The original user query
            report_content: The full content of the research report
            
        Returns:
            Dictionary containing the metadata entry
        """
        # Generate metadata
        metadata = await self.generate_metadata(query, report_content)
        
        # Save to file
        self._save_to_file(metadata)
        
        # Update vector store if ID provided
        if self.vector_store_id:
            await self._update_vector_store(metadata)
            
        return metadata.model_dump()
    
    def _save_to_file(self, metadata: MetaTagEntry) -> None:
        """
        Save metadata to JSON file.
        
        Args:
            metadata: MetaTagEntry object to save
        """
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(self.metadata_file_path)), exist_ok=True)
        
        # Load existing data if file exists
        if os.path.exists(self.metadata_file_path):
            try:
                with open(self.metadata_file_path, 'r') as f:
                    entries = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                entries = []
        else:
            entries = []
            
        # Add new entry
        entries.append(metadata.model_dump())
        
        # Save updated entries
        with open(self.metadata_file_path, 'w') as f:
            json.dump(entries, f, indent=2)
            
    async def _update_vector_store(self, metadata: MetaTagEntry) -> None:
        """
        Update the vector store with the metadata.
        
        Args:
            metadata: MetaTagEntry object to add to vector store
        """
        try:
            # Use the VectorStoreUpdater to handle the actual upload
            updater = VectorStoreUpdater(self.vector_store_id)
            file_id = await updater.update_store(metadata.model_dump())
            
            if file_id:
                print(f"Successfully added metadata to vector store {self.vector_store_id} with file ID {file_id}")
            else:
                print(f"Failed to add metadata to vector store {self.vector_store_id}")
                
        except Exception as e:
            print(f"Error updating vector store: {str(e)}")


def init_meta_tag_agent(config: LLMConfig, vector_store_id: Optional[str] = None) -> MetaTagAgent:
    """
    Initialize a MetaTagAgent.
    
    Args:
        config: LLM configuration
        vector_store_id: ID of the vector store to update (if None, will only save to file)
        
    Returns:
        Initialized MetaTagAgent
    """
    return MetaTagAgent(config, vector_store_id) 