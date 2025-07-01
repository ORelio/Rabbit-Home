'use strict';

var Tools = {
    /**
     * Determine if running in debug mode.
     * In debug mode, alert() dialogs are shown on errors.
     */
    Debug: true,

    /**
     * Log error to console, and show in alert() in debug mode.
     */
    LogError: function(string) {
        var errorMessage = '[Error] ' + string;
        console.error(errorMessage);
        if (Tools.Debug) {
            alert(errorMessage);
        }
    },

    /**
     * Convert timestamp to time
     */
    Timestamp2Time: function(timestamp) {
        if (timestamp != null) {
            var date = new Date(timestamp * 1000);
            var hours = date.getHours();
            var minutes = '0' + date.getMinutes();
            return hours + ':' + minutes.substr(-2);
        } else {
            return ('N/A');
        }
    },

    /**
     * Get current time as string
     */
    CurrentTime: function() {
        return Tools.Timestamp2Time(Date.now());
    },

    /**
     * Capitalize first character
     */
    UpFirst: function(str) {
        return String(str).charAt(0).toUpperCase() + String(str).slice(1);
    },
};

var API = {

    /**
     * Refresh Webpage using a GET request and an optional anchor tag
     * @param {string} anchortag Anchor tag to auto-scroll to (optional)
     */
    RefreshPage: function(anchortag) {
        var random_param_to_force_reload = '';

        if (anchortag !== undefined) {
            anchortag = '#' + anchortag;
            random_param_to_force_reload = '?' + Math.round(Math.random() * 1000000);
        } else {
            anchortag = '';
        }

        window.location.href = window.location.protocol + '//'
            + window.location.hostname
            + window.location.pathname
            + random_param_to_force_reload
            + anchortag;
    },

    /**
     * Perform JSON API Request using XMLHttpRequest
     * @param {string} API request method, e.g. GET or POST
     * @param {string} API endpoint, e.g. /api/submit-data
     * @param {string|Object} body_json JSON data to send, either as object or string
     * @param {function(result): void} success_callback Callback on success containing response data
     * @param {function(result): void} failure_callback (Optional) callback on failure containing response data or status
     */
    ApiRequest: function(method, endpoint, body_json, success_callback, failure_callback) {
        if (typeof body_json === 'object' && body_json !== null) {
            body_json = JSON.stringify(body_json);
        }
        if (typeof body_json !== 'string' || body_json.length == 0) {
            body_json = null;
        }
        var xhr = new XMLHttpRequest();
        xhr.open(method, endpoint, true);
        xhr.setRequestHeader('Content-type', 'application/json');
        xhr.onreadystatechange = function () {
            if (xhr.readyState == 4) {
                if (xhr.status == 200) {
                    var response = xhr.responseText;
                    try {
                        response = JSON.parse(xhr.responseText);
                        try {
                            success_callback(response);
                        } catch (exception) {
                            Tools.LogError(endpoint + ' returned 200 OK but success_callback() failed: ' + exception + '\n\n' + xhr.responseText);
                        }
                    } catch (success_exception) {
                        var errorMessage = Tools.LogError(endpoint + ' returned 200 OK but response body is not JSON: ' + xhr.responseText);
                    }
                } else if (xhr.status >= 400) {
                    response = xhr.responseText;
                    try {
                        response = JSON.parse(xhr.responseText);
                    } catch (failure_exception) {
                        // Not JSON? Keep response as is.
                    }
                    if (typeof failure_callback === 'function') {
                        try {
                            failure_callback(response);
                        } catch (exception) {
                            Tools.LogError(endpoint + ' returned ' + xhr.status + ', then failure_callback() failed: ' + exception + '\n\n' + xhr.responseText);
                        }
                    } else {
                        if (Object.hasOwn(response, 'message')) {
                            alert("Erreur : " + response.message);
                        } else if (Object.hasOwn(response, 'error')) {
                            alert("Erreur : " + response.error);
                        } else {
                            Tools.LogError(endpoint + ' returned code ' + xhr.status + ':\n' + xhr.responseText);
                        }
                    }
                }
            }
        };
        xhr.send(body_json);
    },

    /**
     * Perform API GET API Request
     * Shorthand for ApiRequest('GET', endpoint, null, success_callback, failure_callback)
     */
    GET: function(endpoint, success_callback, failure_callback) {
        return API.ApiRequest('GET', endpoint, null, success_callback, failure_callback);
    },

    /**
     * Perform API POST API Request
     * Shorthand for ApiRequest('POST', endpoint, body_json, success_callback, failure_callback)
     */
    POST: function(endpoint, body_json, success_callback, failure_callback) {
        return API.ApiRequest('POST', endpoint, body_json, success_callback, failure_callback);
    },

    /**
     * Perform API PUT API Request
     * Shorthand for ApiRequest('POST', endpoint, body_json, success_callback, failure_callback)
     */
    PUT: function(endpoint, body_json, success_callback, failure_callback) {
        return API.ApiRequest('PUT', endpoint, body_json, success_callback, failure_callback);
    },

    /**
     * Perform API DELETE API Request
     * Shorthand for ApiRequest('DELETE', endpoint, null, success_callback, failure_callback)
     */
    DELETE: function(endpoint, success_callback, failure_callback) {
        return API.ApiRequest('DELETE', endpoint, null, success_callback, failure_callback);
    },
}
