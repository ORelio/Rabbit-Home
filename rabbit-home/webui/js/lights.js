'use strict';

var Lights = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Lights.RefreshStatus);
    },

    RefreshStatus: function() {
        Tools.ApiToTable(window.API.GET, '/api/v1/lights', 'all_lights', 'light_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_state = document.createElement('div');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'light_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.appendChild(item_state);
                    item_node.onclick = Tools.NamedClickCallback(Lights.Toggle);
                }
                var state_img = document.getElementById('light_' + item_name + '_state');
                state_img.alt = item_data['on'] != null ? (item_data['on'] ? 'ON' : 'OFF') : '?';
                if (item_data['on'] === null) {
                    state_img.src =  'img/lights/unknown.png';
                } else if (item_data['on']) {
                    if (item_data['dimmable'] && item_data['brightness'] <= 50) {
                        state_img.src =  'img/lights/low.png';
                    } else if (item_data['dimmable'] && item_data['brightness'] <= 80) {
                        state_img.src =  'img/lights/medium.png';
                    } else {
                        state_img.src =  'img/lights/high.png';
                    }
                } else {
                    state_img.src =  'img/lights/off.png';
                }
            }
        );
    },

    Toggle: function(light) {
        var light_state = document.getElementById('light_' + light + '_state').alt == 'ON';
        window.API.POST('/api/v1/lights/' + light + '/' + (light_state ? 'off' : 'on'), {}, Lights.RefreshStatus);
    },
}
