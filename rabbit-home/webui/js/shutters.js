'use strict';

var Shutters = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Shutters.RefreshStatus);
        setTimeout(Shutters.RefreshBurst, 1000);
    },

    LastDataChange: 0,

    RefreshBurst: function() {
        if (Shutters.LastDataChange + 10000 > Date.now()) {
            setTimeout(Shutters.RefreshBurst, 1000);
            setTimeout(Shutters.RefreshStatus, 100);
        }
    },

    RefreshStatus: function() {
        Tools.ApiToTable(window.API.GET, '/api/v1/shutters', 'all_shutters', 'shutter_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_state = document.createElement('div');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'shutter_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.appendChild(item_state);

                    var item_value = document.createElement('div');
                    item_value.id = 'shutter_' + item_name + '_value';
                    item_value.className = 'detail';
                    item_node.appendChild(item_value);

                    item_node.onclick = Tools.NamedClickCallback(Shutters.Toggle);
                }

                var state_img = document.getElementById('shutter_' + item_name + '_state');
                var state = 'unknown';
                if (item_data != null) {
                    item_data = parseInt(item_data);
                    if (item_data == 0) {
                        state = 'open';
                    } else if (item_data < 30) {
                        state = 'high';
                    } else if (item_data < 70) {
                        state = 'half';
                    } else if (item_data < 100) {
                        state = 'low';
                    } else {
                        state = 'closed';
                    }
                }
                state_img.src =  'img/shutters/' + state + '.png';
                state_img.alt = state;

                var value_div = document.getElementById('shutter_' + item_name + '_value');
                var value_str = item_data != null ? item_data + ' %' : '';

                if (value_div.innerText != value_str) {
                    value_div.innerText = value_str;
                    Shutters.LastDataChange = Date.now();
                }
            }
        );
    },

    Toggle: function(shutter) {
        Shutters.LastDataChange = Date.now();
        var shutter_state = document.getElementById('shutter_' + shutter + '_state').alt != 'closed';
        window.API.POST('/api/v1/shutters/' + shutter + '/' + (shutter_state ? 'close' : 'open'), {}, Shutters.RefreshBurst);
    },
}
