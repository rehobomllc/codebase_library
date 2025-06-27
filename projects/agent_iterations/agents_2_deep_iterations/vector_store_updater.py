"""
Utility module for interacting with OpenAI's Vector Store.

This module provides functionality to update vector stores with metadata
about completed research sessions, enabling future retrieval and context
enrichment for similar queries.
"""

import os
import json
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import tempfile

# Import conditionally to avoid errors if openai package is not installed
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class VectorStoreUpdater:
    """
    Utility class for updating OpenAI Vector Stores with metadata entries.
    """
    
    def __init__(self, vector_store_id: str, api_key: Optional[str] = None):
        """
        Initialize the VectorStoreUpdater.
        
        Args:
            vector_store_id: ID of the OpenAI vector store to update
            api_key: OpenAI API key (defaults to OPENAI_API_KEY environment variable)
        """
        self.vector_store_id = vector_store_id
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not OPENAI_AVAILABLE:
            print("Warning: OpenAI package not installed. Vector store updates will be simulated.")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                print(f"Successfully initialized OpenAI client for vector store: {self.vector_store_id}")
            except Exception as e:
                print(f"Error initializing OpenAI client: {str(e)}")
                self.client = None
    
    async def update_store(self, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Update the vector store with metadata.
        
        Args:
            metadata: Dictionary containing metadata for a research session
            
        Returns:
            File ID if update was successful, None otherwise
        """
        if not OPENAI_AVAILABLE:
            print(f"[SIMULATED] Would update vector store {self.vector_store_id} with metadata")
            return None
            
        if not self.client:
            print(f"Error: OpenAI client not initialized. Cannot update vector store.")
            return None
            
        # Format metadata into a string for embedding
        content = self._format_metadata(metadata)
        
        # Save a local copy for reference
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_copy_path = os.path.join(os.getcwd(), f"vector_store_metadata_{timestamp}.txt")
        with open(local_copy_path, "w") as local_file:
            local_file.write(content)
        print(f"Saved local copy of metadata file at: {local_copy_path}")
        
        # Create a temporary file with the metadata
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(content)
        
        try:
            print(f"Uploading metadata directly to vector store: {self.vector_store_id}")
            
            # Create a file with the metadata content
            file_creation_response = self.client.files.create(
                file=open(temp_file_path, "rb"),
                purpose="assistants"  # Use assistants purpose as it's compatible with vector stores
            )
            file_id = file_creation_response.id
            print(f"File created with ID: {file_id}")
            print(f"Note: Files with purpose='assistants' can't be downloaded directly. View your local copy at: {local_copy_path}")
            
            # Add the file to the vector store
            try:
                file_add_response = self.client.vector_stores.files.create(
                    vector_store_id=self.vector_store_id,
                    file_id=file_id
                )
                print(f"Successfully added file {file_id} to vector store {self.vector_store_id}")
                return file_id
            except Exception as e:
                print(f"Error adding file to vector store: {str(e)}")
                # Try to clean up the file if we couldn't add it to the vector store
                try:
                    self.client.files.delete(file_id=file_id)
                    print(f"Deleted file {file_id} after failed vector store update")
                except Exception as cleanup_error:
                    print(f"Error cleaning up file: {str(cleanup_error)}")
                return None
                
        except Exception as e:
            print(f"Error during vector store update: {str(e)}")
            return None
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                print(f"Removed temporary file: {temp_file_path}")
    
    def _format_metadata(self, metadata: Dict[str, Any]) -> str:
        """
        Format metadata dictionary into a string for embedding.
        
        Args:
            metadata: Dictionary containing metadata
            
        Returns:
            Formatted string
        """
        # Add timestamp if not present
        if "timestamp" not in metadata or not metadata["timestamp"]:
            metadata["timestamp"] = datetime.now().isoformat()
        
        # Create a formatted content string
        lines = []
        
        # Add main query and timestamp
        lines.append(f"METADATA ENTRY - {metadata['timestamp']}")
        lines.append(f"USER QUERY: {metadata['query']}")
        lines.append("")
        
        # Add summary
        if "summary" in metadata and metadata["summary"]:
            lines.append("SUMMARY:")
            lines.append(metadata["summary"])
            lines.append("")
        
        # Add entities
        if "key_entities" in metadata and metadata["key_entities"]:
            entities = metadata["key_entities"]
            if isinstance(entities, list):
                entities_str = ", ".join(entities)
            else:
                entities_str = str(entities)
            lines.append(f"KEY ENTITIES: {entities_str}")
        
        # Add user intent
        if "user_intent" in metadata and metadata["user_intent"]:
            lines.append(f"USER INTENT: {metadata['user_intent']}")
        
        # Add sentiment
        if "sentiment" in metadata and metadata["sentiment"]:
            lines.append(f"SENTIMENT: {metadata['sentiment']}")
        
        # Add topics
        if "topics" in metadata and metadata["topics"]:
            topics = metadata["topics"]
            if isinstance(topics, list):
                topics_str = ", ".join(topics)
            else:
                topics_str = str(topics)
            lines.append(f"TOPICS: {topics_str}")
        
        # Add content reflection
        if "content_reflection" in metadata and metadata["content_reflection"]:
            lines.append("\nREFLECTION:")
            lines.append(metadata["content_reflection"])
        
        # Add facilities
        if "most_relevant_facilities" in metadata and metadata["most_relevant_facilities"]:
            facilities = metadata["most_relevant_facilities"]
            if isinstance(facilities, list):
                facilities_str = "\n- " + "\n- ".join(facilities)
            else:
                facilities_str = str(facilities)
            lines.append("\nRELEVANT FACILITIES:")
            lines.append(facilities_str)
        
        # Add all remaining fields not specifically handled
        lines.append("\nADDITIONAL METADATA:")
        for key, value in metadata.items():
            if key not in ["query", "timestamp", "summary", "key_entities", 
                          "user_intent", "sentiment", "topics", 
                          "content_reflection", "most_relevant_facilities"]:
                if value:
                    lines.append(f"{key.upper()}: {value}")
        
        return "\n".join(lines)


def create_file_search_tool(vector_store_id: str, max_results: int = 10, include_results: bool = True) -> Dict[str, Any]:
    """
    Create a file search tool configuration for use with the OpenAI Responses API.
    
    Args:
        vector_store_id: ID of the vector store to search
        max_results: Maximum number of results to return
        include_results: Whether to include the search results in the output
        
    Returns:
        Dictionary with file search tool configuration conforming to the FileSearchTool specification
    """
    return {
        "type": "file_search",
        "vector_store_ids": [vector_store_id],  # List of vector store IDs
        "max_num_results": max_results,         # Maximum number of results
        "include_search_results": include_results  # Whether to include results in output
        # Optional parameters:
        # "ranking_options": {...} - Could be added for custom ranking
        # "filters": {...} - Could be added for filtering results
    }


def get_available_vector_stores(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get a list of available vector stores for the current API key.
    
    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY environment variable)
        
    Returns:
        List of vector store information dictionaries
    """
    if not OPENAI_AVAILABLE:
        print("Warning: OpenAI package not installed. Cannot retrieve vector stores.")
        return []
    
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    try:
        response = client.vector_stores.list()
        return [store.model_dump() for store in response.data]
    except Exception as e:
        print(f"Error getting vector stores: {str(e)}")
        return [] 