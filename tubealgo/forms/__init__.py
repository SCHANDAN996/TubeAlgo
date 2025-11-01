# tubealgo/forms/__init__.py

from .auth_forms import SignupForm, LoginForm
from .youtube_forms import PlaylistForm, VideoForm, UploadForm
# <<< बदलाव यहाँ है: PlanForm को SubscriptionPlanForm से बदला गया >>>
from .admin_forms import CouponForm, SubscriptionPlanForm

__all__ = [
    "SignupForm", "LoginForm",
    "PlaylistForm", "VideoForm", "UploadForm",
    # <<< बदलाव यहाँ है: PlanForm को SubscriptionPlanForm से बदला गया >>>
    "CouponForm", "SubscriptionPlanForm"
]
