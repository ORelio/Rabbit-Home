'use strict';

var Alarm = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Alarm.RefreshStatus);
    },

    RefreshStatus: function() {
        window.API.GET('/api/v1/alarm', function(result) {
            var alarm_status = document.getElementById('alarm_status')
            if (alarm_status.alt.length == 0) {
                // initial build
                alarm_status.onclick = Alarm.ShowKeypad;
            }
            if (result != null) {
                if (result.enabled) {
                    alarm_status.src = 'img/alarm/alarm_on.png';
                    alarm_status.alt = 'ON';
                } else {
                    alarm_status.src = 'img/alarm/alarm_off.png';
                    alarm_status.alt = 'OFF';
                }
            } else {
                alarm_status.src = 'img/alarm/alarm_unknown.png';
                alarm_status.alt = 'Unknown';
            }
        });

        Tools.ApiToTable(window.API.GET, '/api/v1/openings', 'all_openings', 'opening_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var name_div = item_node.getElementsByTagName('div')[0];
                    var item_state = document.createElement('span');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'opening_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.insertBefore(item_state, name_div);
                }

                var state_img = document.getElementById('opening_' + item_name + '_state');
                if (state_img.alt != item_data) {
                    if (item_data != null) {
                        if (item_data == 'open') {
                            state_img.src =  'img/alarm/opening_open.png';
                        } else if (item_data == 'closed') {
                            state_img.src =  'img/alarm/opening_closed.png';
                        } else {
                            state_img.src =  'img/alarm/opening_unknown.png';
                        }
                    }
                    state_img.alt = item_data;
                }
            }
        , 1 /* element per row */);

        Tools.ApiToTable(window.API.GET, '/api/v1/cameras', 'all_cameras', 'camera_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_state = document.createElement('div');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'camera_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.appendChild(item_state);

                    var item_time = document.createElement('div');
                    item_time.id = 'camera_' + item_name + '_time';
                    item_time.className = 'detail';
                    item_node.appendChild(item_time);
                }

                var state_img = document.getElementById('camera_' + item_name + '_state');
                var state_desc = document.getElementById('camera_' + item_name + '_time')
                if (state_img.alt != item_data.state) {
                    if (item_data.state == 'online') {
                        state_img.src =  'img/alarm/camera_online.png';
                        state_desc.classList.add('refresh_time')
                        state_desc.innerText = Tools.Timestamp2Time(item_data.refreshed);
                    } else {
                        state_img.src =  'img/alarm/camera_offline.png';
                        state_desc.classList.remove('refresh_time')
                        state_desc.innerText = 'Hors ligne';
                    }
                }

            }
        , 3 /* element per row */);
    },

    TypedCode: '',

    ShowKeypad: function() {
        document.getElementById('alarm_data').style.visibility = 'hidden';
        document.getElementById('alarm_keypad').style.display = 'block';
    },

    KeypadCancel: function() {
        document.getElementById('alarm_data').style.visibility = 'visible';
        document.getElementById('alarm_keypad').style.display = 'none';
        Alarm.TypedCode = '';
    },

    KeyPress: function(digit) {
        Alarm.TypedCode = Alarm.TypedCode + digit;
    },

    KeypadOk: function(digit) {
        window.API.POST('/api/v1/alarm/toggle', {'code': Alarm.TypedCode}, Alarm.RefreshStatus);
        Alarm.KeypadCancel();
    }
}
