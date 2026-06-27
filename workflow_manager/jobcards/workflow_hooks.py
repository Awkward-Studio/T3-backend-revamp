"""
Workflow extension hooks for future stages.

Post Delivery Inspection is not implemented yet; callers should use these
placeholders so the transition can be wired without changing call sites later.
"""

from jobcards.models import JobCard


def can_start_post_delivery_inspection(jobcard: JobCard) -> bool:
    """Return True when pro-forma invoice exists and PDI has not started."""
    return (
        jobcard.job_card_status >= 4
        and jobcard.workflow_status != JobCard.WorkflowStatus.POST_DELIVERY_INSPECTION_PENDING
    )


def mark_post_delivery_inspection_pending(jobcard: JobCard) -> JobCard:
    """
    Future hook: set workflow status after pro-forma invoice generation.
    Not invoked by the application yet.
    """
    jobcard.workflow_status = JobCard.WorkflowStatus.POST_DELIVERY_INSPECTION_PENDING
    jobcard.save(update_fields=["workflow_status", "updated_at"])
    return jobcard
