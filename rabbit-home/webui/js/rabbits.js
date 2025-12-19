'use strict';

var Rabbits = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Rabbits.RefreshStatus);
    },

    LastDataChange: 0,

    RefreshBurst: function() {
        if (Rabbits.LastDataChange + 60000 > Date.now()) {
            setTimeout(Rabbits.RefreshBurst, 1000);
            setTimeout(Rabbits.RefreshStatus, 100);
        }
    },

    RefreshStatus: function() {
        Tools.ApiToTable(window.API.GET, '/api/v1/rabbits', 'all_rabbits', 'rabbit_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_state = document.createElement('div');
                    var item_state_img = document.createElement('img');
                    item_state_img.id = 'rabbit_' + item_name + '_state';
                    item_state.appendChild(item_state_img);
                    item_node.appendChild(item_state);
                    item_node.onclick = Tools.NamedClickCallback(Rabbits.Toggle);
                }

                var state_img = document.getElementById('rabbit_' + item_name + '_state');
                if (state_img.alt != item_data) {
                    if (item_data != null) {
                        if (item_data == "awake") {
                            state_img.src =  'img/rabbits/awake.png';
                        } else if (item_data == "asleep") {
                            state_img.src =  'img/rabbits/asleep.png';
                        } else {
                            state_img.src =  'img/rabbits/offline.png';
                        }
                    }
                    state_img.alt = item_data;
                    Rabbits.LastDataChange = Date.now();
                }
            }
        , 2 /* elements per row */);
    },

    Toggle: function(rabbit) {
        Rabbits.LastDataChange = Date.now();
        var state_img = document.getElementById('rabbit_' + rabbit + '_state');
        if (state_img.alt != 'offline' && state_img.src.indexOf('wait') === -1) {
            window.API.POST('/api/v1/rabbits/' + rabbit + '/' + (state_img.alt == 'asleep' ? 'wakeup' : 'sleep'), {}, Rabbits.RefreshBurst);
            state_img.src = state_img.src.replace('.png', '-wait.png');
        }
    },
}
