from apps.accounts.admin_site import register

from .models import AnswerRecord, FailureCase, RetrievalResult, RetrievalRun, UserFeedback

register(RetrievalRun, RetrievalResult, AnswerRecord, UserFeedback, FailureCase)
