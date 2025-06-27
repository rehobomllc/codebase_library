import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

from utils.tool_provider import get_tool_provider

logger = logging.getLogger(__name__)

class DocumentType(Enum):
    GOOGLE_DOC = "google_doc"
    GOOGLE_SHEET = "google_sheet"
    FORM = "form"
    REPORT = "report"
    TEMPLATE = "template"
    VERIFICATION = "verification"

class DocumentStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    TEMPLATE = "template"

@dataclass
class DocumentVersion:
    """Represents a version of a document"""
    version_id: str
    document_id: str
    version_number: int
    created_at: datetime
    created_by: str
    changes_summary: str
    document_url: Optional[str] = None
    backup_content: Optional[str] = None

@dataclass
class TreatmentDocument:
    """Represents a treatment-related document"""
    document_id: str
    user_id: str
    document_type: DocumentType
    status: DocumentStatus
    title: str
    description: str
    google_doc_id: Optional[str] = None
    google_sheet_id: Optional[str] = None
    template_id: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    tags: List[str] = None
    versions: List[DocumentVersion] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}
        if self.tags is None:
            self.tags = []
        if self.versions is None:
            self.versions = []

class DocumentTemplate:
    """Represents a document template"""
    def __init__(self, template_id: str, name: str, document_type: DocumentType, 
                 template_content: str, variables: List[str] = None):
        self.template_id = template_id
        self.name = name
        self.document_type = document_type
        self.template_content = template_content
        self.variables = variables or []
        self.created_at = datetime.now()
        self.usage_count = 0

class DocumentManager:
    """Manages documents, templates, and Google Drive integration"""
    
    def __init__(self):
        self.documents: Dict[str, TreatmentDocument] = {}
        self.templates: Dict[str, DocumentTemplate] = {}
        self.tool_provider = None
        self._setup_templates()
    
    async def initialize(self):
        """Initialize the document manager with tool provider"""
        self.tool_provider = get_tool_provider()
        if not self.tool_provider:
            logger.warning("Tool provider not available - document operations will be limited")
        else:
            logger.info("Document manager initialized with Google tools")
    
    def _setup_templates(self):
        """Setup predefined document templates"""
        
        # Insurance Verification Template
        insurance_template = DocumentTemplate(
            template_id="insurance_verification_v1",
            name="Insurance Verification Document",
            document_type=DocumentType.GOOGLE_DOC,
            template_content="""
# Insurance Verification Report

**Patient Information:**
- Name: {{patient_name}}
- Date of Birth: {{date_of_birth}}
- Member ID: {{member_id}}
- Group Number: {{group_number}}

**Insurance Information:**
- Provider: {{insurance_provider}}
- Plan Type: {{plan_type}}
- Effective Date: {{effective_date}}
- Expiration Date: {{expiration_date}}

**Coverage Details:**
- Mental Health Coverage: {{mental_health_coverage}}
- Substance Abuse Coverage: {{substance_abuse_coverage}}
- Copay: {{copay}}
- Deductible: {{deductible}}
- Out-of-Pocket Maximum: {{out_of_pocket_max}}

**In-Network Providers:**
{{in_network_providers}}

**Verification Status:** {{verification_status}}
**Verified By:** {{verified_by}}
**Verification Date:** {{verification_date}}

**Notes:**
{{additional_notes}}
            """,
            variables=["patient_name", "date_of_birth", "member_id", "group_number", 
                      "insurance_provider", "plan_type", "effective_date", "expiration_date",
                      "mental_health_coverage", "substance_abuse_coverage", "copay", 
                      "deductible", "out_of_pocket_max", "in_network_providers",
                      "verification_status", "verified_by", "verification_date", "additional_notes"]
        )
        
        # Treatment Plan Template
        treatment_plan_template = DocumentTemplate(
            template_id="treatment_plan_v1",
            name="Treatment Plan Document",
            document_type=DocumentType.GOOGLE_DOC,
            template_content="""
# Treatment Plan for {{patient_name}}

**Plan Created:** {{plan_date}}
**Treatment Provider:** {{provider_name}}
**Treatment Facility:** {{facility_name}}

## Patient Information
- Name: {{patient_name}}
- Date of Birth: {{date_of_birth}}
- Emergency Contact: {{emergency_contact}}

## Treatment Goals
{{treatment_goals}}

## Treatment Approach
- Primary Treatment Type: {{primary_treatment}}
- Session Frequency: {{session_frequency}}
- Estimated Duration: {{estimated_duration}}

## Medications (if applicable)
{{medications}}

## Support Resources
{{support_resources}}

## Milestones and Check-ins
{{milestones}}

## Emergency Protocols
{{emergency_protocols}}

**Plan Approved By:** {{approved_by}}
**Date:** {{approval_date}}
            """,
            variables=["patient_name", "plan_date", "provider_name", "facility_name",
                      "date_of_birth", "emergency_contact", "treatment_goals", 
                      "primary_treatment", "session_frequency", "estimated_duration",
                      "medications", "support_resources", "milestones", "emergency_protocols",
                      "approved_by", "approval_date"]
        )
        
        # Intake Form Template
        intake_form_template = DocumentTemplate(
            template_id="intake_form_v1",
            name="Treatment Intake Form",
            document_type=DocumentType.FORM,
            template_content="""
# Treatment Intake Form

**Personal Information:**
- Full Name: {{full_name}}
- Date of Birth: {{date_of_birth}}
- Address: {{address}}
- Phone: {{phone}}
- Email: {{email}}
- Emergency Contact: {{emergency_contact}}

**Insurance Information:**
- Insurance Provider: {{insurance_provider}}
- Member ID: {{member_id}}
- Group Number: {{group_number}}

**Medical History:**
- Current Medications: {{current_medications}}
- Allergies: {{allergies}}
- Previous Treatment: {{previous_treatment}}
- Mental Health History: {{mental_health_history}}

**Current Situation:**
- Reason for Seeking Treatment: {{reason_for_treatment}}
- Current Symptoms: {{current_symptoms}}
- Support System: {{support_system}}
- Goals for Treatment: {{treatment_goals}}

**Consent and Signatures:**
- Treatment Consent: {{treatment_consent}}
- Privacy Policy Agreement: {{privacy_agreement}}
- Patient Signature: {{patient_signature}}
- Date: {{signature_date}}
            """,
            variables=["full_name", "date_of_birth", "address", "phone", "email",
                      "emergency_contact", "insurance_provider", "member_id", "group_number",
                      "current_medications", "allergies", "previous_treatment", "mental_health_history",
                      "reason_for_treatment", "current_symptoms", "support_system", 
                      "treatment_goals", "treatment_consent", "privacy_agreement", 
                      "patient_signature", "signature_date"]
        )
        
        # Facility Research Spreadsheet Template
        facility_spreadsheet_template = DocumentTemplate(
            template_id="facility_research_v1",
            name="Treatment Facility Research Spreadsheet",
            document_type=DocumentType.GOOGLE_SHEET,
            template_content="""
Facility Name | Address | Phone | Website | Treatment Types | Insurance Accepted | Availability | Rating | Notes | Contact Date | Next Steps
{{facility_data}}
            """,
            variables=["facility_data"]
        )
        
        # Progress Report Template
        progress_report_template = DocumentTemplate(
            template_id="progress_report_v1",
            name="Treatment Progress Report",
            document_type=DocumentType.REPORT,
            template_content="""
# Treatment Progress Report

**Patient:** {{patient_name}}
**Report Period:** {{report_start_date}} to {{report_end_date}}
**Generated:** {{report_date}}

## Summary
{{progress_summary}}

## Goals Achievement
{{goals_achievement}}

## Challenges and Barriers
{{challenges}}

## Medication Compliance
{{medication_compliance}}

## Appointment Attendance
- Scheduled Appointments: {{scheduled_appointments}}
- Attended Appointments: {{attended_appointments}}
- Missed Appointments: {{missed_appointments}}
- Attendance Rate: {{attendance_rate}}%

## Milestones Reached
{{milestones_reached}}

## Recommendations
{{recommendations}}

## Next Review Date
{{next_review_date}}

**Report Compiled By:** {{compiled_by}}
            """,
            variables=["patient_name", "report_start_date", "report_end_date", "report_date",
                      "progress_summary", "goals_achievement", "challenges", "medication_compliance",
                      "scheduled_appointments", "attended_appointments", "missed_appointments",
                      "attendance_rate", "milestones_reached", "recommendations", 
                      "next_review_date", "compiled_by"]
        )
        
        # Store templates
        self.templates = {
            insurance_template.template_id: insurance_template,
            treatment_plan_template.template_id: treatment_plan_template,
            intake_form_template.template_id: intake_form_template,
            facility_spreadsheet_template.template_id: facility_spreadsheet_template,
            progress_report_template.template_id: progress_report_template
        }
        
        logger.info(f"Initialized {len(self.templates)} document templates")
    
    async def create_document_from_template(
        self,
        user_id: str,
        template_id: str,
        title: str,
        variables: Dict[str, Any],
        description: str = "",
        tags: List[str] = None
    ) -> str:
        """Create a new document from a template"""
        
        if template_id not in self.templates:
            raise ValueError(f"Template {template_id} not found")
        
        template = self.templates[template_id]
        template.usage_count += 1
        
        # Generate document content by replacing variables
        content = template.template_content
        for var, value in variables.items():
            content = content.replace(f"{{{{{var}}}}}", str(value))
        
        # Create document
        document_id = str(uuid.uuid4())
        
        # Create Google Doc or Sheet based on template type
        google_doc_id = None
        google_sheet_id = None
        
        if template.document_type == DocumentType.GOOGLE_DOC:
            google_doc_id = await self._create_google_doc(title, content)
        elif template.document_type == DocumentType.GOOGLE_SHEET:
            google_sheet_id = await self._create_google_sheet(title, content)
        
        # Create document record
        document = TreatmentDocument(
            document_id=document_id,
            user_id=user_id,
            document_type=template.document_type,
            status=DocumentStatus.ACTIVE,
            title=title,
            description=description,
            google_doc_id=google_doc_id,
            google_sheet_id=google_sheet_id,
            template_id=template_id,
            metadata={
                "template_name": template.name,
                "variables_used": list(variables.keys()),
                "creation_method": "template"
            },
            tags=tags or []
        )
        
        # Create initial version
        version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            document_id=document_id,
            version_number=1,
            created_at=datetime.now(),
            created_by=user_id,
            changes_summary="Initial document creation from template",
            document_url=self._get_document_url(google_doc_id, google_sheet_id)
        )
        
        document.versions.append(version)
        self.documents[document_id] = document
        
        logger.info(f"Created document {document_id} from template {template_id}")
        return document_id
    
    async def create_blank_document(
        self,
        user_id: str,
        document_type: DocumentType,
        title: str,
        description: str = "",
        content: str = "",
        tags: List[str] = None
    ) -> str:
        """Create a blank document"""
        
        document_id = str(uuid.uuid4())
        
        # Create Google Doc or Sheet
        google_doc_id = None
        google_sheet_id = None
        
        if document_type == DocumentType.GOOGLE_DOC:
            google_doc_id = await self._create_google_doc(title, content)
        elif document_type == DocumentType.GOOGLE_SHEET:
            google_sheet_id = await self._create_google_sheet(title, content)
        
        # Create document record
        document = TreatmentDocument(
            document_id=document_id,
            user_id=user_id,
            document_type=document_type,
            status=DocumentStatus.ACTIVE,
            title=title,
            description=description,
            google_doc_id=google_doc_id,
            google_sheet_id=google_sheet_id,
            metadata={
                "creation_method": "blank"
            },
            tags=tags or []
        )
        
        # Create initial version
        version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            document_id=document_id,
            version_number=1,
            created_at=datetime.now(),
            created_by=user_id,
            changes_summary="Initial blank document creation",
            document_url=self._get_document_url(google_doc_id, google_sheet_id)
        )
        
        document.versions.append(version)
        self.documents[document_id] = document
        
        logger.info(f"Created blank document {document_id}")
        return document_id
    
    async def update_document(
        self,
        document_id: str,
        updated_by: str,
        changes_summary: str,
        new_content: Optional[str] = None,
        metadata_updates: Dict[str, Any] = None
    ) -> str:
        """Update an existing document and create a new version"""
        
        if document_id not in self.documents:
            raise ValueError(f"Document {document_id} not found")
        
        document = self.documents[document_id]
        
        # Update Google Doc/Sheet if content provided
        if new_content and document.google_doc_id:
            await self._update_google_doc(document.google_doc_id, new_content)
        elif new_content and document.google_sheet_id:
            await self._update_google_sheet(document.google_sheet_id, new_content)
        
        # Update metadata
        if metadata_updates:
            document.metadata.update(metadata_updates)
        
        document.updated_at = datetime.now()
        
        # Create new version
        version_number = max([v.version_number for v in document.versions]) + 1
        version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            document_id=document_id,
            version_number=version_number,
            created_at=datetime.now(),
            created_by=updated_by,
            changes_summary=changes_summary,
            document_url=self._get_document_url(document.google_doc_id, document.google_sheet_id)
        )
        
        document.versions.append(version)
        
        logger.info(f"Updated document {document_id} - Version {version_number}")
        return version.version_id
    
    async def get_document(self, document_id: str) -> Optional[TreatmentDocument]:
        """Get a document by ID"""
        return self.documents.get(document_id)
    
    async def get_user_documents(
        self,
        user_id: str,
        document_type: Optional[DocumentType] = None,
        status: Optional[DocumentStatus] = None,
        tags: List[str] = None
    ) -> List[TreatmentDocument]:
        """Get documents for a user with optional filters"""
        
        documents = []
        for doc in self.documents.values():
            if doc.user_id != user_id:
                continue
            
            if document_type and doc.document_type != document_type:
                continue
            
            if status and doc.status != status:
                continue
            
            if tags and not any(tag in doc.tags for tag in tags):
                continue
            
            documents.append(doc)
        
        # Sort by updated_at descending
        documents.sort(key=lambda d: d.updated_at, reverse=True)
        return documents
    
    async def archive_document(self, document_id: str) -> bool:
        """Archive a document"""
        if document_id not in self.documents:
            return False
        
        self.documents[document_id].status = DocumentStatus.ARCHIVED
        self.documents[document_id].updated_at = datetime.now()
        
        logger.info(f"Archived document {document_id}")
        return True
    
    async def delete_document(self, document_id: str, permanent: bool = False) -> bool:
        """Delete a document (soft delete by default)"""
        if document_id not in self.documents:
            return False
        
        if permanent:
            # Delete from Google Drive
            document = self.documents[document_id]
            if document.google_doc_id:
                await self._delete_google_doc(document.google_doc_id)
            if document.google_sheet_id:
                await self._delete_google_sheet(document.google_sheet_id)
            
            # Remove from memory
            del self.documents[document_id]
            logger.info(f"Permanently deleted document {document_id}")
        else:
            # Soft delete
            self.documents[document_id].status = DocumentStatus.DELETED
            self.documents[document_id].updated_at = datetime.now()
            logger.info(f"Soft deleted document {document_id}")
        
        return True
    
    async def search_documents(
        self,
        user_id: str,
        query: str,
        document_types: List[DocumentType] = None
    ) -> List[TreatmentDocument]:
        """Search documents by title, description, or content"""
        
        results = []
        query_lower = query.lower()
        
        for doc in self.documents.values():
            if doc.user_id != user_id:
                continue
            
            if document_types and doc.document_type not in document_types:
                continue
            
            if doc.status == DocumentStatus.DELETED:
                continue
            
            # Search in title, description, and tags
            searchable_text = f"{doc.title} {doc.description} {' '.join(doc.tags)}".lower()
            
            if query_lower in searchable_text:
                results.append(doc)
        
        return results
    
    async def get_templates(self) -> List[DocumentTemplate]:
        """Get all available templates"""
        return list(self.templates.values())
    
    async def backup_document(self, document_id: str) -> bool:
        """Create a backup of a document"""
        if document_id not in self.documents:
            return False
        
        document = self.documents[document_id]
        
        # Get current content from Google Drive
        content = ""
        if document.google_doc_id:
            content = await self._get_google_doc_content(document.google_doc_id)
        elif document.google_sheet_id:
            content = await self._get_google_sheet_content(document.google_sheet_id)
        
        # Store backup in the latest version
        if document.versions:
            document.versions[-1].backup_content = content
        
        logger.info(f"Backed up document {document_id}")
        return True
    
    # Google Drive Integration Methods
    
    async def _create_google_doc(self, title: str, content: str) -> Optional[str]:
        """Create a Google Doc"""
        if not self.tool_provider:
            logger.warning("Cannot create Google Doc - tool provider not available")
            return None
        
        try:
            tools = await self.tool_provider.get_tools(toolkits=["google"])
            
            # Use Google.CreateDocumentFromText if available
            create_doc_tool = None
            for tool in tools:
                if hasattr(tool, 'name') and 'CreateDocumentFromText' in str(tool.name):
                    create_doc_tool = tool
                    break
            
            if not create_doc_tool:
                # Fallback to CreateBlankDocument
                for tool in tools:
                    if hasattr(tool, 'name') and 'CreateBlankDocument' in str(tool.name):
                        create_doc_tool = tool
                        break
            
            if create_doc_tool:
                # Simulate document creation (replace with actual tool call)
                doc_id = f"google_doc_{uuid.uuid4().hex[:8]}"
                logger.info(f"Created Google Doc: {title} (ID: {doc_id})")
                return doc_id
            else:
                logger.warning("No suitable Google Doc creation tool found")
                return None
            
        except Exception as e:
            logger.error(f"Failed to create Google Doc: {e}")
            return None
    
    async def _create_google_sheet(self, title: str, content: str) -> Optional[str]:
        """Create a Google Sheet"""
        if not self.tool_provider:
            logger.warning("Cannot create Google Sheet - tool provider not available")
            return None
        
        try:
            tools = await self.tool_provider.get_tools(toolkits=["google"])
            
            # Use Google.CreateSpreadsheet if available
            create_sheet_tool = None
            for tool in tools:
                if hasattr(tool, 'name') and 'CreateSpreadsheet' in str(tool.name):
                    create_sheet_tool = tool
                    break
            
            if create_sheet_tool:
                # Simulate sheet creation (replace with actual tool call)
                sheet_id = f"google_sheet_{uuid.uuid4().hex[:8]}"
                logger.info(f"Created Google Sheet: {title} (ID: {sheet_id})")
                return sheet_id
            else:
                logger.warning("No suitable Google Sheet creation tool found")
                return None
            
        except Exception as e:
            logger.error(f"Failed to create Google Sheet: {e}")
            return None
    
    async def _update_google_doc(self, doc_id: str, content: str) -> bool:
        """Update a Google Doc"""
        try:
            # This would use Google API to update the document
            logger.info(f"Updated Google Doc {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Google Doc {doc_id}: {e}")
            return False
    
    async def _update_google_sheet(self, sheet_id: str, content: str) -> bool:
        """Update a Google Sheet"""
        try:
            # This would use Google API to update the sheet
            logger.info(f"Updated Google Sheet {sheet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Google Sheet {sheet_id}: {e}")
            return False
    
    async def _get_google_doc_content(self, doc_id: str) -> str:
        """Get content from a Google Doc"""
        try:
            # This would use Google API to get document content
            return f"Content of Google Doc {doc_id}"
        except Exception as e:
            logger.error(f"Failed to get Google Doc content {doc_id}: {e}")
            return ""
    
    async def _get_google_sheet_content(self, sheet_id: str) -> str:
        """Get content from a Google Sheet"""
        try:
            # This would use Google API to get sheet content
            return f"Content of Google Sheet {sheet_id}"
        except Exception as e:
            logger.error(f"Failed to get Google Sheet content {sheet_id}: {e}")
            return ""
    
    async def _delete_google_doc(self, doc_id: str) -> bool:
        """Delete a Google Doc"""
        try:
            # This would use Google API to delete the document
            logger.info(f"Deleted Google Doc {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Google Doc {doc_id}: {e}")
            return False
    
    async def _delete_google_sheet(self, sheet_id: str) -> bool:
        """Delete a Google Sheet"""
        try:
            # This would use Google API to delete the sheet
            logger.info(f"Deleted Google Sheet {sheet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Google Sheet {sheet_id}: {e}")
            return False
    
    def _get_document_url(self, doc_id: Optional[str], sheet_id: Optional[str]) -> Optional[str]:
        """Get the URL for a Google document"""
        if doc_id:
            return f"https://docs.google.com/document/d/{doc_id}/edit"
        elif sheet_id:
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return None

# Global document manager instance
document_manager = DocumentManager()

async def get_document_manager() -> DocumentManager:
    """Get the global document manager instance"""
    return document_manager

async def initialize_document_manager():
    """Initialize the document manager"""
    await document_manager.initialize() 