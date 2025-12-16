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

    /**
     * Switch UI tab
     */
    SwitchTab: function(btn) {
        var tab_id = btn.getAttribute('data-tab-id');
        var all_tabs = document.getElementsByClassName("tab");
        var all_buttons = document.getElementsByClassName("tab_button");
        for (var i = 0; i < all_tabs.length; i++) {
            all_tabs[i].style.display = all_tabs[i].id === tab_id ? 'block' : 'none';
        }
        for (var i = 0; i < all_buttons.length; i++) {
            if (all_buttons[i].getAttribute('data-tab-id') == tab_id) {
                all_buttons[i].classList.add('selected');
            } else {
                all_buttons[i].classList.remove('selected');
            }
        }
    },

    /**
     * Make an API GET request and dynamically populate results into a destination HTML table
     * @param {function} api_function API function, e.g. API.GET (see API object).
     * @param {string} api_endpoint API endpoint, e.g. "/api/v1/endpoint". Endpoint shall return JSON {"result1": {..data..}, "result2": {..data..}, ...}.
     * @param {string} table_id Destination table ID, e.g. "my_table"
     * @param {string} cell_id_prefix Prefix, e.g. "mydata_" for table cells. Cells will have IDs like mydata_result1, mydata_result2, etc.
     * @param {function(string, object, Node, boolean): void} cell_callback Callback taking result name, result data, <td> node, initial_build (True: build node. False: refresh data)
     * @param {int} elements_per_row Optionally override the default amount of elements per row, which is 4.
     */
     ApiToTable: function(api_function, api_endpoint, table_id, cell_id_prefix, cell_callback, elements_per_row) {
         if (elements_per_row === undefined) {
             elements_per_row = 4;
         }
         api_function(api_endpoint, function(api_data) {
            var all_result_names = Object.keys(api_data);
            var current_table_row = null;
            for (var i=0; i < all_result_names.length; i++) {
                var result_name = all_result_names[i];
                var result_cell = document.getElementById(cell_id_prefix + result_name);
                var initial_build = (result_cell === null);
                if (initial_build) {
                    if (i%elements_per_row == 0) {
                        current_table_row = document.createElement('tr');
                        document.getElementById(table_id).appendChild(current_table_row);
                    }

                    result_cell = document.createElement('td');
                    result_cell.id = cell_id_prefix + result_name;
                    result_cell.setAttribute('data-name', result_name);
                    result_cell.style.width = (100 / elements_per_row).toString() + '%';

                    var cell_name = document.createElement('div');
                    cell_name.innerText = Tools.UpFirst(result_name);
                    cell_name.className = 'name';
                    result_cell.appendChild(cell_name);

                    current_table_row.appendChild(result_cell);
                }
                cell_callback(result_name, api_data[result_name], result_cell, initial_build);
            }
        });
     },

    /**
     * Make a callback which receives the name of clicked cell instead of the click event
     * Cell name comes from the data-name attribute set by theApiToTable() function.
     */
    NamedClickCallback: function(callback) {
        return function(click) {
            var click_target = click.target;
            if (click_target.getAttribute('data-name') == null) {
                click_target = click_target.parentElement;
                if (click_target.getAttribute('data-name') == null) {
                    click_target = click_target.parentElement;
                }
            }
            callback(click_target.getAttribute('data-name'));
        }
    },

    /**
     * Automatically call the provided refresh function every 5 minutes or the specified time interval
     */
    ScheduleAutoRefresh: function(callback, refresh_time) {
        if (refresh_time === undefined) {
            refresh_time = 300000; // 5 minutes
        }
        setTimeout(callback, 100);
        setTimeout(function() { Tools.ScheduleAutoRefresh(callback, refresh_time); }, refresh_time);
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
     * @param {string} method API request method, e.g. GET or POST
     * @param {string} endpoint API endpoint, e.g. /api/submit-data
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
        if (window.document.documentMode) {
            // bypass IE11 XMLHttpRequest response caching
            var timestamp = String(Date.now());
            if (endpoint.indexOf('?') !== -1) {
                endpoint = endpoint + '&_ts=' + timestamp;
            } else {
                endpoint = endpoint + '?_ts=' + timestamp;
            }
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
                        if (response.hasOwnProperty('message')) {
                            alert("Erreur : " + response.message);
                        } else if (response.hasOwnProperty('error')) {
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
