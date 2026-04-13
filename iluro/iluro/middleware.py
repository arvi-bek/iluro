import logging

from django.shortcuts import render


logger = logging.getLogger("iluro.request_errors")


class FriendlyErrorPagesMiddleware:
    """
    Force branded 404 page even while DEBUG=True.
    This keeps local/demo sessions cleaner and avoids exposing the technical 404 page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "Unhandled request error",
                extra={
                    "request_path": request.path,
                    "request_method": request.method,
                    "user_id": getattr(getattr(request, "user", None), "id", None),
                    "username": getattr(getattr(request, "user", None), "username", ""),
                    "post_keys": sorted(request.POST.keys()) if request.method == "POST" else [],
                    "has_photo_upload": bool(getattr(request, "FILES", {}).get("photo")),
                    "remove_photo": request.POST.get("remove_photo") == "on" if request.method == "POST" else False,
                    "remote_addr": request.META.get("REMOTE_ADDR", ""),
                    "user_agent": request.META.get("HTTP_USER_AGENT", "")[:240],
                },
            )
            raise

        if response.status_code == 404:
            content_type = response.headers.get("Content-Type", "")
            accepts_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            if accepts_json or content_type.startswith("application/json"):
                return response
            return render(request, "404.html", status=404)

        return response
