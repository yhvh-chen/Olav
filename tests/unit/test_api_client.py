"""Unit tests for api_client module.

Tests for HTTP client functionality for calling external APIs.
"""

from unittest.mock import Mock, patch

import pytest
import httpx

from olav.tools.api_client import _execute_request, api_call


# =============================================================================
# Test api_call
# =============================================================================


class TestApiCall:
    """Tests for api_call function."""

    def test_api_call_missing_url_env_var(self):
        """Test when API URL environment variable is not set."""
        with patch("os.getenv", return_value=None):
            result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/endpoint/"})

            assert "Error: NETBOX_URL environment variable not set" in result

    def test_api_call_with_token_auth(self):
        """Test API call with token authentication."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "test-token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request", return_value="Success"):
                result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/dcim/devices/"})

                assert result == "Success"

    def test_api_call_with_basic_auth(self):
        """Test API call with basic authentication."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_USER": "admin",
                "NETBOX_PASSWORD": "password",
            }.get(x)

            with patch("olav.tools.api_client._execute_request", return_value="Success"):
                result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/dcim/devices/"})

                assert result == "Success"

    def test_api_call_url_building(self):
        """Test that URL is built correctly."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com/api/",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request") as mock_exec:
                mock_exec.return_value = "Success"

                api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/dcim/devices/"})

                # Verify URL was built correctly (trailing slash handled)
                call_kwargs = mock_exec.call_args.kwargs
                assert call_kwargs["url"] == "https://netbox.example.com/api/dcim/devices/"

    def test_api_call_with_params(self):
        """Test API call with query parameters."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request", return_value="Success"):
                result = api_call.invoke({
                    "system": "netbox",
                    "method": "GET",
                    "endpoint": "/api/dcim/devices/",
                    "params": {"name": "R1"}
                })

                assert result == "Success"

    def test_api_call_with_body(self):
        """Test API call with request body."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request", return_value="Success"):
                result = api_call.invoke({
                    "system": "netbox",
                    "method": "PATCH",
                    "endpoint": "/api/dcim/devices/1/",
                    "body": {"status": "active"}
                })

                assert result == "Success"

    def test_api_call_handles_http_status_error(self):
        """Test handling of HTTPStatusError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request") as mock_exec:
                mock_exec.side_effect = httpx.HTTPStatusError("Not found", request=Mock(), response=mock_response)

                result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/notfound/"})

                assert "Error: HTTP 404" in result
                assert "Not found" in result

    def test_api_call_handles_request_error(self):
        """Test handling of RequestError."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request") as mock_exec:
                mock_exec.side_effect = httpx.RequestError("Connection failed")

                result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/test/"})

                assert "Error: Request failed" in result

    def test_api_call_handles_general_exception(self):
        """Test handling of general exceptions."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
            }.get(x)

            with patch("olav.tools.api_client._execute_request") as mock_exec:
                mock_exec.side_effect = Exception("Unexpected error")

                result = api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/test/"})

                assert "Error: Unexpected error" in result

    def test_api_call_token_overrides_basic_auth(self):
        """Test that token auth is used when both are available."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda x: {
                "NETBOX_URL": "https://netbox.example.com",
                "NETBOX_TOKEN": "token",
                "NETBOX_USER": "admin",
                "NETBOX_PASSWORD": "password",
            }.get(x)

            with patch("olav.tools.api_client._execute_request") as mock_exec:
                mock_exec.return_value = "Success"

                api_call.invoke({"system": "netbox", "method": "GET", "endpoint": "/api/test/"})

                # When token is present, username/password should be None
                call_kwargs = mock_exec.call_args.kwargs
                assert call_kwargs["username"] is None
                assert call_kwargs["password"] is None


# =============================================================================
# Test _execute_request
# =============================================================================


class TestExecuteRequest:
    """Tests for _execute_request function."""

    def test_execute_request_get(self):
        """Test GET request."""
        mock_response = Mock()
        mock_response.text = '{"results": []}'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="GET",
                url="https://api.example.com/test",
                params=None,
                body=None,
                headers={"Content-Type": "application/json"},
                username=None,
                password=None,
            )

            assert result == '{"results": []}'
            mock_client.get.assert_called_once()

    def test_execute_request_post(self):
        """Test POST request."""
        mock_response = Mock()
        mock_response.text = '{"id": 1}'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="POST",
                url="https://api.example.com/test",
                params=None,
                body={"name": "test"},
                headers={"Content-Type": "application/json"},
                username=None,
                password=None,
            )

            assert result == '{"id": 1}'
            mock_client.post.assert_called_once()

    def test_execute_request_put(self):
        """Test PUT request."""
        mock_response = Mock()
        mock_response.text = '{"id": 1}'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.put.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="PUT",
                url="https://api.example.com/test/1",
                params=None,
                body={"name": "updated"},
                headers={"Content-Type": "application/json"},
                username=None,
                password=None,
            )

            assert result == '{"id": 1}'
            mock_client.put.assert_called_once()

    def test_execute_request_patch(self):
        """Test PATCH request."""
        mock_response = Mock()
        mock_response.text = '{"id": 1}'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="PATCH",
                url="https://api.example.com/test/1",
                params=None,
                body={"status": "active"},
                headers={"Content-Type": "application/json"},
                username=None,
                password=None,
            )

            assert result == '{"id": 1}'
            mock_client.patch.assert_called_once()

    def test_execute_request_delete(self):
        """Test DELETE request."""
        mock_response = Mock()
        mock_response.text = '{"deleted": true}'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.delete.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="DELETE",
                url="https://api.example.com/test/1",
                params=None,
                body=None,
                headers={"Content-Type": "application/json"},
                username=None,
                password=None,
            )

            assert result == '{"deleted": true}'
            mock_client.delete.assert_called_once()

    def test_execute_request_unsupported_method(self):
        """Test unsupported HTTP method."""
        result = _execute_request(
            method="INVALID",
            url="https://api.example.com/test",
            params=None,
            body=None,
            headers={},
            username=None,
            password=None,
        )

        assert "Error: Unsupported HTTP method: INVALID" in result

    def test_execute_request_with_params(self):
        """Test request with query parameters."""
        mock_response = Mock()
        mock_response.text = '[]'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="GET",
                url="https://api.example.com/test",
                params={"name": "R1", "status": "active"},
                body=None,
                headers={},
                username=None,
                password=None,
            )

            # Verify params were passed
            call_kwargs = mock_client.get.call_args.kwargs
            assert "params" in call_kwargs

    def test_execute_request_with_basic_auth(self):
        """Test request with basic authentication."""
        mock_response = Mock()
        mock_response.text = '[]'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="GET",
                url="https://api.example.com/test",
                params=None,
                body=None,
                headers={},
                username="admin",
                password="password",
            )

            # Verify auth was passed
            call_kwargs = mock_client.get.call_args.kwargs
            assert "auth" in call_kwargs
            assert call_kwargs["auth"] == ("admin", "password")

    def test_execute_request_case_insensitive_method(self):
        """Test that HTTP method is case-insensitive."""
        mock_response = Mock()
        mock_response.text = '[]'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="get",  # lowercase
                url="https://api.example.com/test",
                params=None,
                body=None,
                headers={},
                username=None,
                password=None,
            )

            assert result == '[]'
            mock_client.get.assert_called_once()

    def test_execute_request_includes_timeout(self):
        """Test that timeout is included in request."""
        mock_response = Mock()
        mock_response.text = '[]'
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _execute_request(
                method="GET",
                url="https://api.example.com/test",
                params=None,
                body=None,
                headers={},
                username=None,
                password=None,
            )

            # Verify timeout was set
            call_kwargs = mock_client.get.call_args.kwargs
            assert call_kwargs["timeout"] == 30.0

    def test_execute_request_raises_http_status_error(self):
        """Test that HTTPStatusError is raised on error response."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock(side_effect=httpx.HTTPStatusError("Error", request=Mock(), response=mock_response))

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                _execute_request(
                    method="GET",
                    url="https://api.example.com/test",
                    params=None,
                    body=None,
                    headers={},
                    username=None,
                    password=None,
                )
