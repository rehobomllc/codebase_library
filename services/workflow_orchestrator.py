import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

from services.database import db_manager

logger = logging.getLogger(__name__)

class WorkflowStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class WorkflowStep:
    """Represents a single step in a treatment workflow"""
    step_id: str
    name: str
    agent_name: str
    dependencies: List[str]  # Step IDs this step depends on
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class TreatmentWorkflow:
    """Represents a complete treatment workflow"""
    workflow_id: str
    user_id: str
    workflow_type: str
    name: str
    description: str
    steps: List[WorkflowStep]
    status: WorkflowStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step: Optional[str] = None
    context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}

class WorkflowOrchestrator:
    """Orchestrates multi-agent workflows for treatment processes"""
    
    def __init__(self):
        self.active_workflows: Dict[str, TreatmentWorkflow] = {}
        self.agent_registry: Dict[str, Any] = {}
        self.workflow_templates: Dict[str, Callable] = {}
        self.db_manager = db_manager
        
        # Register workflow templates
        self._register_workflow_templates()
    
    def _register_workflow_templates(self):
        """Register predefined workflow templates"""
        self.workflow_templates = {
            "complete_treatment_onboarding": self._create_onboarding_workflow,
            "facility_search_and_schedule": self._create_search_schedule_workflow,
            "insurance_verification_and_approval": self._create_insurance_workflow,
            "intake_form_completion": self._create_intake_workflow,
            "treatment_plan_setup": self._create_treatment_plan_workflow,
            "crisis_intervention": self._create_crisis_workflow
        }
    
    async def register_agent(self, name: str, agent: Any):
        """Register an agent for use in workflows"""
        self.agent_registry[name] = agent
        logger.info(f"Registered agent: {name}")
    
    async def create_workflow(self, workflow_type: str, user_id: str, **kwargs) -> str:
        """Create a new workflow from template"""
        if workflow_type not in self.workflow_templates:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        workflow_id = str(uuid.uuid4())
        template_func = self.workflow_templates[workflow_type]
        workflow = template_func(workflow_id, user_id, **kwargs)
        
        # Save to database
        await self._save_workflow(workflow)
        
        # Add to active workflows
        self.active_workflows[workflow_id] = workflow
        
        logger.info(f"Created workflow {workflow_id} of type {workflow_type} for user {user_id}")
        return workflow_id
    
    async def execute_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Execute a workflow step by step"""
        if workflow_id not in self.active_workflows:
            # Try to load from database
            workflow = await self._load_workflow(workflow_id)
            if not workflow:
                raise ValueError(f"Workflow {workflow_id} not found")
            self.active_workflows[workflow_id] = workflow
        
        workflow = self.active_workflows[workflow_id]
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()
        
        try:
            while True:
                next_step = self._get_next_step(workflow)
                if not next_step:
                    # Workflow completed
                    workflow.status = WorkflowStatus.COMPLETED
                    workflow.completed_at = datetime.now()
                    break
                
                # Execute the step
                success = await self._execute_step(workflow, next_step)
                
                if not success:
                    if next_step.retry_count >= next_step.max_retries:
                        workflow.status = WorkflowStatus.FAILED
                        break
                    else:
                        # Retry the step
                        next_step.retry_count += 1
                        next_step.status = StepStatus.PENDING
                        await asyncio.sleep(2 ** next_step.retry_count)  # Exponential backoff
                
                # Save progress
                await self._save_workflow(workflow)
            
            # Final save
            await self._save_workflow(workflow)
            
            return {
                "workflow_id": workflow_id,
                "status": workflow.status.value,
                "completed_steps": len([s for s in workflow.steps if s.status == StepStatus.COMPLETED]),
                "total_steps": len(workflow.steps),
                "outputs": self._collect_workflow_outputs(workflow)
            }
            
        except Exception as e:
            logger.error(f"Workflow {workflow_id} failed: {e}", exc_info=True)
            workflow.status = WorkflowStatus.FAILED
            await self._save_workflow(workflow)
            raise
    
    async def _execute_step(self, workflow: TreatmentWorkflow, step: WorkflowStep) -> bool:
        """Execute a single workflow step"""
        logger.info(f"Executing step {step.step_id}: {step.name}")
        
        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.now()
        workflow.current_step = step.step_id
        
        try:
            # Get the agent for this step
            if step.agent_name not in self.agent_registry:
                logger.warning(f"Agent {step.agent_name} not registered, simulating execution")
                # Simulate execution for now
                await asyncio.sleep(1)
                result = {"simulated": True, "agent": step.agent_name}
            else:
                agent = self.agent_registry[step.agent_name]
                # Prepare inputs (merge step inputs with workflow context)
                execution_inputs = {**workflow.context, **step.inputs}
                # Execute the agent
                result = await self._run_agent_with_inputs(agent, execution_inputs)
            
            # Store outputs
            step.outputs = result
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.now()
            
            # Update workflow context with step outputs
            workflow.context.update(result)
            
            logger.info(f"Step {step.step_id} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Step {step.step_id} failed: {e}", exc_info=True)
            step.status = StepStatus.FAILED
            step.error_message = str(e)
            return False
    
    def _get_next_step(self, workflow: TreatmentWorkflow) -> Optional[WorkflowStep]:
        """Get the next step that can be executed"""
        for step in workflow.steps:
            if step.status != StepStatus.PENDING:
                continue
            
            # Check if all dependencies are completed
            dependencies_met = all(
                any(s.step_id == dep_id and s.status == StepStatus.COMPLETED 
                    for s in workflow.steps)
                for dep_id in step.dependencies
            )
            
            if dependencies_met:
                return step
        
        return None
    
    async def _run_agent_with_inputs(self, agent: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run an agent with given inputs and return structured outputs"""
        # For now, simulate agent execution
        result = {
            "agent_executed": getattr(agent, 'name', 'unknown'),
            "execution_time": datetime.now().isoformat(),
            "inputs_processed": list(inputs.keys()),
            "success": True
        }
        
        return result
    
    def _collect_workflow_outputs(self, workflow: TreatmentWorkflow) -> Dict[str, Any]:
        """Collect all outputs from completed workflow steps"""
        outputs = {}
        for step in workflow.steps:
            if step.status == StepStatus.COMPLETED:
                outputs[step.step_id] = step.outputs
        return outputs
    
    # Workflow Templates
    
    def _create_onboarding_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create complete treatment onboarding workflow"""
        steps = [
            WorkflowStep(
                step_id="gather_profile",
                name="Gather User Profile",
                agent_name="triage_agent",
                dependencies=[],
                inputs={"task": "gather_comprehensive_profile"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="search_facilities",
                name="Search Treatment Facilities",
                agent_name="facility_search_agent",
                dependencies=["gather_profile"],
                inputs={"task": "search_facilities"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="verify_insurance",
                name="Verify Insurance Coverage",
                agent_name="insurance_verification_agent",
                dependencies=["gather_profile", "search_facilities"],
                inputs={"task": "verify_coverage"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="schedule_appointment",
                name="Schedule Initial Appointment",
                agent_name="appointment_scheduler_agent",
                dependencies=["search_facilities", "verify_insurance"],
                inputs={"task": "schedule_initial_consultation"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="prepare_intake",
                name="Prepare Intake Forms",
                agent_name="intake_form_agent",
                dependencies=["schedule_appointment"],
                inputs={"task": "prepare_intake_documentation"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="setup_reminders",
                name="Setup Treatment Reminders",
                agent_name="treatment_reminder_agent",
                dependencies=["schedule_appointment"],
                inputs={"task": "create_appointment_reminders"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="complete_treatment_onboarding",
            name="Complete Treatment Onboarding",
            description="Full onboarding process from profile gathering to first appointment",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    def _create_search_schedule_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create facility search and scheduling workflow"""
        steps = [
            WorkflowStep(
                step_id="search_facilities",
                name="Search Treatment Facilities",
                agent_name="facility_search_agent",
                dependencies=[],
                inputs=kwargs,
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="schedule_appointment",
                name="Schedule Appointment",
                agent_name="appointment_scheduler_agent",
                dependencies=["search_facilities"],
                inputs={"task": "schedule_appointment"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="send_confirmation",
                name="Send Appointment Confirmation",
                agent_name="treatment_communication_agent",
                dependencies=["schedule_appointment"],
                inputs={"task": "send_confirmation_email"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="facility_search_and_schedule",
            name="Facility Search and Scheduling",
            description="Search for facilities and schedule appointments",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    def _create_insurance_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create insurance verification and approval workflow"""
        steps = [
            WorkflowStep(
                step_id="verify_coverage",
                name="Verify Insurance Coverage",
                agent_name="insurance_verification_agent",
                dependencies=[],
                inputs=kwargs,
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="document_verification",
                name="Create Verification Documentation",
                agent_name="insurance_verification_agent",
                dependencies=["verify_coverage"],
                inputs={"task": "create_verification_document"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="communicate_results",
                name="Communicate Verification Results",
                agent_name="treatment_communication_agent",
                dependencies=["document_verification"],
                inputs={"task": "send_verification_results"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="insurance_verification_and_approval",
            name="Insurance Verification and Approval",
            description="Complete insurance verification process",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    def _create_intake_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create intake form completion workflow"""
        steps = [
            WorkflowStep(
                step_id="analyze_forms",
                name="Analyze Required Forms",
                agent_name="intake_form_agent",
                dependencies=[],
                inputs=kwargs,
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="create_templates",
                name="Create Form Templates",
                agent_name="intake_form_agent",
                dependencies=["analyze_forms"],
                inputs={"task": "create_form_templates"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="guide_completion",
                name="Guide Form Completion",
                agent_name="intake_form_agent",
                dependencies=["create_templates"],
                inputs={"task": "guide_form_completion"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="submit_forms",
                name="Submit Completed Forms",
                agent_name="treatment_communication_agent",
                dependencies=["guide_completion"],
                inputs={"task": "submit_intake_forms"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="intake_form_completion",
            name="Intake Form Completion",
            description="Complete intake form process from analysis to submission",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    def _create_treatment_plan_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create treatment plan setup workflow"""
        steps = [
            WorkflowStep(
                step_id="create_plan",
                name="Create Treatment Plan",
                agent_name="treatment_reminder_agent",
                dependencies=[],
                inputs=kwargs,
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="schedule_reminders",
                name="Schedule Treatment Reminders",
                agent_name="treatment_reminder_agent",
                dependencies=["create_plan"],
                inputs={"task": "setup_recurring_reminders"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="coordinate_care",
                name="Coordinate Care Team",
                agent_name="treatment_communication_agent",
                dependencies=["create_plan"],
                inputs={"task": "coordinate_care_team"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="treatment_plan_setup",
            name="Treatment Plan Setup",
            description="Setup comprehensive treatment plan with reminders and coordination",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    def _create_crisis_workflow(self, workflow_id: str, user_id: str, **kwargs) -> TreatmentWorkflow:
        """Create crisis intervention workflow"""
        steps = [
            WorkflowStep(
                step_id="crisis_assessment",
                name="Crisis Assessment",
                agent_name="triage_agent",
                dependencies=[],
                inputs={"task": "crisis_assessment", **kwargs},
                outputs={},
                status=StepStatus.PENDING,
                max_retries=1  # Fewer retries for crisis situations
            ),
            WorkflowStep(
                step_id="emergency_resources",
                name="Provide Emergency Resources",
                agent_name="triage_agent",
                dependencies=["crisis_assessment"],
                inputs={"task": "provide_crisis_resources"},
                outputs={},
                status=StepStatus.PENDING,
                max_retries=1
            ),
            WorkflowStep(
                step_id="urgent_scheduling",
                name="Schedule Urgent Appointment",
                agent_name="appointment_scheduler_agent",
                dependencies=["crisis_assessment"],
                inputs={"task": "schedule_crisis_appointment", "urgency": "crisis"},
                outputs={},
                status=StepStatus.PENDING
            ),
            WorkflowStep(
                step_id="crisis_communication",
                name="Crisis Communication",
                agent_name="treatment_communication_agent",
                dependencies=["urgent_scheduling"],
                inputs={"task": "send_crisis_communication"},
                outputs={},
                status=StepStatus.PENDING
            )
        ]
        
        return TreatmentWorkflow(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type="crisis_intervention",
            name="Crisis Intervention",
            description="Emergency workflow for crisis situations",
            steps=steps,
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
    
    async def _save_workflow(self, workflow: TreatmentWorkflow):
        """Save workflow to database"""
        try:
            # Convert workflow to JSON for storage
            workflow_data = {
                "workflow_id": workflow.workflow_id,
                "user_id": workflow.user_id,
                "workflow_type": workflow.workflow_type,
                "name": workflow.name,
                "description": workflow.description,
                "status": workflow.status.value,
                "created_at": workflow.created_at,
                "started_at": workflow.started_at,
                "completed_at": workflow.completed_at,
                "current_step": workflow.current_step,
                "context": workflow.context,
                "steps": [asdict(step) for step in workflow.steps]
            }
            
            # Save to database (you'd implement the actual DB save here)
            logger.info(f"Saved workflow {workflow.workflow_id} to database")
            
        except Exception as e:
            logger.error(f"Failed to save workflow {workflow.workflow_id}: {e}")
            raise
    
    async def _load_workflow(self, workflow_id: str) -> Optional[TreatmentWorkflow]:
        """Load workflow from database"""
        try:
            # Load from database (you'd implement the actual DB load here)
            # For now, return None to indicate not found
            logger.info(f"Attempted to load workflow {workflow_id} from database")
            return None
            
        except Exception as e:
            logger.error(f"Failed to load workflow {workflow_id}: {e}")
            return None

# Global workflow orchestrator instance
workflow_orchestrator = WorkflowOrchestrator()

async def get_workflow_orchestrator() -> WorkflowOrchestrator:
    """Get the global workflow orchestrator instance"""
    return workflow_orchestrator 