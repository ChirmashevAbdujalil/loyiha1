from .dashboard import dashboard  # noqa: F401
from .notifications import (  # noqa: F401
    notification_feed,
    notification_list,
    notification_open,
    notification_read_all,
    profile,
)
from .people import (  # noqa: F401
    faculty_delete,
    faculty_edit,
    faculty_list,
    tutor_create,
    tutor_delete,
    tutor_detail,
    tutor_edit,
    tutor_list,
)
from .reports import report, report_export  # noqa: F401
from .tasks import (  # noqa: F401
    assignment_detail,
    assignment_review,
    assignment_submit,
    review_queue,
    submission_file,
    task_create,
    task_delete,
    task_detail,
    task_edit,
    task_file,
    task_list,
)
