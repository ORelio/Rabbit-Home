'use strict';

var Plugs = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Plugs.RefreshStatus);
    },

    RefreshStatus: function() {
        Tools.ApiToTable(window.API.GET, '/api/v1/plugs', 'all_plugs', 'plug_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_state = document.createElement('div');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'plug_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.appendChild(item_state);
                    item_node.onclick = Tools.NamedClickCallback(Plugs.Toggle);
                }
                var state_img = document.getElementById('plug_' + item_name + '_state');
                state_img.alt = item_data != null ? (item_data ? 'ON' : 'OFF') : '?';
                if (item_data === null) {
                    state_img.src = 'img/plugs/unknown.png';
                } else if (item_data) {
                    state_img.src = 'img/plugs/on.png';
                } else {
                    state_img.src = 'img/plugs/off.png';
                }
            }
        );
    },

    Toggle: function(plug) {
        var plug_state = document.getElementById('plug_' + plug + '_state').alt == 'ON';
        window.API.POST('/api/v1/plugs/' + plug + '/' + (plug_state ? 'off' : 'on'), {}, Plugs.RefreshStatus);
    },
}
