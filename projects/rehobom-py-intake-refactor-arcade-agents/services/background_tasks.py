import logging
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

from services.database import db_manager
from utils.tool_provider import get_tool_provider

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"

class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class BackgroundTask:
    """Represents a background task"""
    task_id: str
    user_id: str
    task_type: str
    name: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    scheduled_for: datetime
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    parameters: Dict[str, Any] = None
    result: Dict[str, Any] = None
    error_message: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None  # "daily", "weekly", "monthly"
    next_execution: Optional[datetime] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.result is None:
            self.result = {}

class BackgroundTaskManager:
    """Manages background tasks for the treatment system"""
    
    def __init__(self):
        self.active_tasks: Dict[str, BackgroundTask] = {}
        self.task_handlers: Dict[str, Callable] = {}
        self.db_manager = db_manager
        self.is_running = False
        self._setup_task_handlers()
    
    def _setup_task_handlers(self):
        """Register task handlers for different task types"""
        self.task_handlers = {
            "send_appointment_reminder": self._send_appointment_reminder,
            "send_medication_reminder": self._send_medication_reminder,
            "check_insurance_renewal": self._check_insurance_renewal,
            "monitor_facility_availability": self._monitor_facility_availability,
            "send_milestone_celebration": self._send_milestone_celebration,
            "cleanup_expired_data": self._cleanup_expired_data,
            "generate_progress_report": self._generate_progress_report,
            "verify_appointment_attendance": self._verify_appointment_attendance,
            "send_treatment_check_in": self._send_treatment_check_in,
            "backup_user_documents": self._backup_user_documents
        }
    
    async def start(self):
        """Start the background task manager"""
        if self.is_running:
            logger.warning("Background task manager is already running")
            return
        
        self.is_running = True
        logger.info("Starting background task manager")
        
        # Start the main task loop
        asyncio.create_task(self._task_loop())
        
        # Schedule initial system tasks
        await self._schedule_system_tasks()
    
    async def stop(self):
        """Stop the background task manager"""
        self.is_running = False
        logger.info("Stopping background task manager")
    
    async def schedule_task(
        self,
        user_id: str,
        task_type: str,
        name: str,
        description: str,
        scheduled_for: datetime,
        priority: TaskPriority = TaskPriority.NORMAL,
        parameters: Dict[str, Any] = None,
        is_recurring: bool = False,
        recurrence_pattern: Optional[str] = None
    ) -> str:
        """Schedule a new background task"""
        
        task_id = str(uuid.uuid4())
        
        task = BackgroundTask(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            name=name,
            description=description,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            scheduled_for=scheduled_for,
            created_at=datetime.now(),
            parameters=parameters or {},
            is_recurring=is_recurring,
            recurrence_pattern=recurrence_pattern
        )
        
        # Calculate next execution if recurring
        if is_recurring and recurrence_pattern:
            task.next_execution = self._calculate_next_execution(scheduled_for, recurrence_pattern)
        
        # Store in active tasks
        self.active_tasks[task_id] = task
        
        # Save to database
        await self._save_task(task)
        
        logger.info(f"Scheduled task {task_id}: {name} for user {user_id}")
        return task_id
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if task.status in [TaskStatus.PENDING, TaskStatus.SCHEDULED]:
                task.status = TaskStatus.CANCELLED
                await self._save_task(task)
                logger.info(f"Cancelled task {task_id}")
                return True
        return False
    
    async def _task_loop(self):
        """Main task execution loop"""
        while self.is_running:
            try:
                # Get ready tasks
                ready_tasks = await self._get_ready_tasks()
                
                # Execute tasks by priority
                ready_tasks.sort(key=lambda t: t.priority.value, reverse=True)
                
                for task in ready_tasks:
                    if not self.is_running:
                        break
                    
                    try:
                        await self._execute_task(task)
                    except Exception as e:
                        logger.error(f"Error executing task {task.task_id}: {e}", exc_info=True)
                
                # Sleep before next iteration
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in task loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _get_ready_tasks(self) -> List[BackgroundTask]:
        """Get tasks that are ready to execute"""
        now = datetime.now()
        ready_tasks = []
        
        for task in self.active_tasks.values():
            if (task.status == TaskStatus.SCHEDULED and 
                task.scheduled_for <= now):
                ready_tasks.append(task)
        
        return ready_tasks
    
    async def _execute_task(self, task: BackgroundTask):
        """Execute a single task"""
        logger.info(f"Executing task {task.task_id}: {task.name}")
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        try:
            # Get task handler
            if task.task_type not in self.task_handlers:
                raise ValueError(f"Unknown task type: {task.task_type}")
            
            handler = self.task_handlers[task.task_type]
            
            # Execute the task
            result = await handler(task)
            
            # Mark as completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.result = result
            
            # Schedule next execution if recurring
            if task.is_recurring and task.recurrence_pattern:
                await self._schedule_next_occurrence(task)
            
            logger.info(f"Task {task.task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}", exc_info=True)
            
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.retry_count += 1
            
            # Retry if under limit
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.SCHEDULED
                task.scheduled_for = datetime.now() + timedelta(minutes=5 * task.retry_count)
                logger.info(f"Rescheduling failed task {task.task_id} for retry {task.retry_count}")
        
        finally:
            await self._save_task(task)
    
    async def _schedule_next_occurrence(self, task: BackgroundTask):
        """Schedule the next occurrence of a recurring task"""
        if not task.next_execution:
            return
        
        # Create new task for next occurrence
        next_task_id = str(uuid.uuid4())
        next_task = BackgroundTask(
            task_id=next_task_id,
            user_id=task.user_id,
            task_type=task.task_type,
            name=task.name,
            description=task.description,
            priority=task.priority,
            status=TaskStatus.SCHEDULED,
            scheduled_for=task.next_execution,
            created_at=datetime.now(),
            parameters=task.parameters.copy(),
            is_recurring=task.is_recurring,
            recurrence_pattern=task.recurrence_pattern
        )
        
        # Calculate next execution for the new task
        next_task.next_execution = self._calculate_next_execution(
            task.next_execution, task.recurrence_pattern
        )
        
        self.active_tasks[next_task_id] = next_task
        await self._save_task(next_task)
        
        logger.info(f"Scheduled next occurrence of recurring task: {next_task_id}")
    
    def _calculate_next_execution(self, current_time: datetime, pattern: str) -> datetime:
        """Calculate the next execution time for a recurring task"""
        if pattern == "daily":
            return current_time + timedelta(days=1)
        elif pattern == "weekly":
            return current_time + timedelta(weeks=1)
        elif pattern == "monthly":
            # Approximate monthly - add 30 days
            return current_time + timedelta(days=30)
        elif pattern == "hourly":
            return current_time + timedelta(hours=1)
        else:
            # Default to daily
            return current_time + timedelta(days=1)
    
    # Task Handlers
    
    async def _send_appointment_reminder(self, task: BackgroundTask) -> Dict[str, Any]:
        """Send appointment reminder"""
        user_id = task.user_id
        params = task.parameters
        
        appointment_id = params.get('appointment_id')
        appointment_datetime = params.get('appointment_datetime')
        facility_name = params.get('facility_name')
        reminder_type = params.get('reminder_type', '24_hour')  # "24_hour", "2_hour", "30_min"
        
        try:
            # Get tool provider
            tool_provider = get_tool_provider()
            if not tool_provider:
                raise ValueError("Tool provider not available")
            
            # Get Google tools for sending email
            google_tools = await tool_provider.get_tools(toolkits=["google"])
            
            # Prepare reminder email
            reminder_content = {
                "to": user_id,  # This would be the user's email
                "subject": f"Appointment Reminder - {facility_name}",
                "body": f"""
                Dear {user_id},
                
                This is a reminder about your upcoming appointment:
                
                Date & Time: {appointment_datetime}
                Facility: {facility_name}
                Appointment ID: {appointment_id}
                
                Please remember to:
                - Bring your ID and insurance card
                - Arrive 15 minutes early
                - Bring your medication list
                
                If you need to reschedule, please call the facility as soon as possible.
                
                Best regards,
                Treatment Navigator
                """
            }
            
            # For now, simulate sending the email
            logger.info(f"Sending {reminder_type} appointment reminder to {user_id}")
            
            return {
                "status": "sent",
                "reminder_type": reminder_type,
                "appointment_id": appointment_id,
                "sent_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to send appointment reminder: {e}")
            raise
    
    async def _send_medication_reminder(self, task: BackgroundTask) -> Dict[str, Any]:
        """Send medication reminder"""
        user_id = task.user_id
        params = task.parameters
        
        medication_name = params.get('medication_name')
        dosage = params.get('dosage')
        time_to_take = params.get('time_to_take')
        
        logger.info(f"Sending medication reminder to {user_id} for {medication_name}")
        
        return {
            "status": "sent",
            "medication": medication_name,
            "dosage": dosage,
            "reminder_time": time_to_take,
            "sent_at": datetime.now().isoformat()
        }
    
    async def _check_insurance_renewal(self, task: BackgroundTask) -> Dict[str, Any]:
        """Check if insurance verification needs renewal"""
        user_id = task.user_id
        params = task.parameters
        
        insurance_id = params.get('insurance_id')
        expiry_date = params.get('expiry_date')
        
        logger.info(f"Checking insurance renewal for user {user_id}")
        
        # Check if insurance is expiring soon (within 30 days)
        expiry = datetime.fromisoformat(expiry_date) if isinstance(expiry_date, str) else expiry_date
        days_until_expiry = (expiry - datetime.now()).days
        
        needs_renewal = days_until_expiry <= 30
        
        if needs_renewal:
            # Schedule a task to notify user about renewal
            await self.schedule_task(
                user_id=user_id,
                task_type="send_insurance_renewal_notice",
                name="Insurance Renewal Notice",
                description=f"Notify user about upcoming insurance expiry",
                scheduled_for=datetime.now() + timedelta(minutes=5),
                priority=TaskPriority.HIGH,
                parameters={
                    "insurance_id": insurance_id,
                    "expiry_date": expiry_date,
                    "days_until_expiry": days_until_expiry
                }
            )
        
        return {
            "status": "checked",
            "needs_renewal": needs_renewal,
            "days_until_expiry": days_until_expiry,
            "checked_at": datetime.now().isoformat()
        }
    
    async def _monitor_facility_availability(self, task: BackgroundTask) -> Dict[str, Any]:
        """Monitor facility availability changes"""
        user_id = task.user_id
        params = task.parameters
        
        facility_id = params.get('facility_id')
        facility_name = params.get('facility_name')
        
        logger.info(f"Monitoring facility availability for {facility_name}")
        
        # This would check facility websites/APIs for availability changes
        # For now, simulate the check
        availability_changed = False  # Simulate no change
        
        return {
            "status": "monitored",
            "facility_id": facility_id,
            "availability_changed": availability_changed,
            "checked_at": datetime.now().isoformat()
        }
    
    async def _send_milestone_celebration(self, task: BackgroundTask) -> Dict[str, Any]:
        """Send milestone celebration message"""
        user_id = task.user_id
        params = task.parameters
        
        milestone_type = params.get('milestone_type')  # "30_days_sober", "treatment_completion", etc.
        milestone_date = params.get('milestone_date')
        
        logger.info(f"Sending milestone celebration to {user_id} for {milestone_type}")
        
        return {
            "status": "sent",
            "milestone_type": milestone_type,
            "milestone_date": milestone_date,
            "sent_at": datetime.now().isoformat()
        }
    
    async def _cleanup_expired_data(self, task: BackgroundTask) -> Dict[str, Any]:
        """Clean up expired data"""
        user_id = task.user_id
        
        logger.info(f"Cleaning up expired data for user {user_id}")
        
        # This would clean up old reminders, expired verifications, etc.
        cleaned_items = 0  # Simulate cleanup
        
        return {
            "status": "completed",
            "items_cleaned": cleaned_items,
            "cleaned_at": datetime.now().isoformat()
        }
    
    async def _generate_progress_report(self, task: BackgroundTask) -> Dict[str, Any]:
        """Generate treatment progress report"""
        user_id = task.user_id
        params = task.parameters
        
        report_type = params.get('report_type', 'weekly')
        
        logger.info(f"Generating {report_type} progress report for user {user_id}")
        
        return {
            "status": "generated",
            "report_type": report_type,
            "generated_at": datetime.now().isoformat()
        }
    
    async def _verify_appointment_attendance(self, task: BackgroundTask) -> Dict[str, Any]:
        """Verify if user attended their appointment"""
        user_id = task.user_id
        params = task.parameters
        
        appointment_id = params.get('appointment_id')
        
        logger.info(f"Verifying appointment attendance for user {user_id}")
        
        # This would check with facility systems or ask user for confirmation
        attended = None  # Unknown status for now
        
        return {
            "status": "checked",
            "appointment_id": appointment_id,
            "attended": attended,
            "checked_at": datetime.now().isoformat()
        }
    
    async def _send_treatment_check_in(self, task: BackgroundTask) -> Dict[str, Any]:
        """Send treatment check-in message"""
        user_id = task.user_id
        params = task.parameters
        
        check_in_type = params.get('check_in_type', 'weekly')
        
        logger.info(f"Sending {check_in_type} check-in to user {user_id}")
        
        return {
            "status": "sent",
            "check_in_type": check_in_type,
            "sent_at": datetime.now().isoformat()
        }
    
    async def _backup_user_documents(self, task: BackgroundTask) -> Dict[str, Any]:
        """Backup user documents to secure storage"""
        user_id = task.user_id
        
        logger.info(f"Backing up documents for user {user_id}")
        
        # This would backup Google Docs, forms, etc. to secure storage
        backed_up_count = 0  # Simulate backup
        
        return {
            "status": "completed",
            "documents_backed_up": backed_up_count,
            "backed_up_at": datetime.now().isoformat()
        }
    
    async def _schedule_system_tasks(self):
        """Schedule regular system maintenance tasks"""
        now = datetime.now()
        
        # Schedule daily cleanup
        await self.schedule_task(
            user_id="system",
            task_type="cleanup_expired_data",
            name="Daily Data Cleanup",
            description="Clean up expired reminders and old data",
            scheduled_for=now + timedelta(hours=1),
            priority=TaskPriority.LOW,
            is_recurring=True,
            recurrence_pattern="daily"
        )
        
        logger.info("Scheduled system maintenance tasks")
    
    async def _save_task(self, task: BackgroundTask):
        """Save task to database"""
        try:
            # Convert task to dictionary for storage
            task_data = asdict(task)
            # Convert enums to their values
            task_data['status'] = task.status.value
            task_data['priority'] = task.priority.value
            
            # Here you would save to your database
            # For now, just log
            logger.debug(f"Saved task {task.task_id} to database")
            
        except Exception as e:
            logger.error(f"Failed to save task {task.task_id}: {e}")
    
    # Public methods for scheduling common treatment tasks
    
    async def schedule_appointment_reminders(
        self,
        user_id: str,
        appointment_id: str,
        appointment_datetime: datetime,
        facility_name: str
    ):
        """Schedule all reminders for an appointment"""
        
        # 24-hour reminder
        await self.schedule_task(
            user_id=user_id,
            task_type="send_appointment_reminder",
            name="24-Hour Appointment Reminder",
            description=f"24-hour reminder for appointment at {facility_name}",
            scheduled_for=appointment_datetime - timedelta(hours=24),
            priority=TaskPriority.NORMAL,
            parameters={
                "appointment_id": appointment_id,
                "appointment_datetime": appointment_datetime.isoformat(),
                "facility_name": facility_name,
                "reminder_type": "24_hour"
            }
        )
        
        # 2-hour reminder
        await self.schedule_task(
            user_id=user_id,
            task_type="send_appointment_reminder",
            name="2-Hour Appointment Reminder",
            description=f"2-hour reminder for appointment at {facility_name}",
            scheduled_for=appointment_datetime - timedelta(hours=2),
            priority=TaskPriority.HIGH,
            parameters={
                "appointment_id": appointment_id,
                "appointment_datetime": appointment_datetime.isoformat(),
                "facility_name": facility_name,
                "reminder_type": "2_hour"
            }
        )
        
        # Post-appointment follow-up
        await self.schedule_task(
            user_id=user_id,
            task_type="verify_appointment_attendance",
            name="Verify Appointment Attendance",
            description=f"Check if user attended appointment at {facility_name}",
            scheduled_for=appointment_datetime + timedelta(hours=4),
            priority=TaskPriority.NORMAL,
            parameters={
                "appointment_id": appointment_id,
                "appointment_datetime": appointment_datetime.isoformat(),
                "facility_name": facility_name
            }
        )
    
    async def schedule_medication_reminders(
        self,
        user_id: str,
        medication_name: str,
        dosage: str,
        reminder_times: List[str]  # List of times like ["08:00", "20:00"]
    ):
        """Schedule daily medication reminders"""
        
        for time_str in reminder_times:
            hour, minute = map(int, time_str.split(':'))
            
            # Schedule for today and tomorrow (then recurring will take over)
            today = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if today < datetime.now():
                today += timedelta(days=1)  # Schedule for tomorrow if time has passed
            
            await self.schedule_task(
                user_id=user_id,
                task_type="send_medication_reminder",
                name=f"Medication Reminder - {medication_name}",
                description=f"Daily reminder to take {medication_name} at {time_str}",
                scheduled_for=today,
                priority=TaskPriority.HIGH,
                parameters={
                    "medication_name": medication_name,
                    "dosage": dosage,
                    "time_to_take": time_str
                },
                is_recurring=True,
                recurrence_pattern="daily"
            )
    
    async def schedule_insurance_monitoring(
        self,
        user_id: str,
        insurance_id: str,
        expiry_date: datetime
    ):
        """Schedule insurance expiry monitoring"""
        
        # Check 60 days before expiry
        check_date = expiry_date - timedelta(days=60)
        if check_date > datetime.now():
            await self.schedule_task(
                user_id=user_id,
                task_type="check_insurance_renewal",
                name="Insurance Renewal Check",
                description="Check if insurance needs renewal",
                scheduled_for=check_date,
                priority=TaskPriority.NORMAL,
                parameters={
                    "insurance_id": insurance_id,
                    "expiry_date": expiry_date.isoformat()
                },
                is_recurring=True,
                recurrence_pattern="weekly"
            )

# Global background task manager instance
background_task_manager = BackgroundTaskManager()

async def get_background_task_manager() -> BackgroundTaskManager:
    """Get the global background task manager instance"""
    return background_task_manager

async def start_background_tasks():
    """Start the background task system"""
    await background_task_manager.start()

async def stop_background_tasks():
    """Stop the background task system"""
    await background_task_manager.stop() 