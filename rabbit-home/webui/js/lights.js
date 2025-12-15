'use strict';

var Lights = {

    RefreshStatus: function() {
        window.API.GET('/api/v1/lights', function(result) {
            var lights = Object.keys(result);
            var tr = null;
            for (var i=0; i < lights.length; i++) {
                var light = lights[i];

                var light_node = document.getElementById('light_' + light);
                var light_node_state_img = null;

                // Create node in list if not present yet
                if (light_node === null) {

                    //Add at most 4 elements per row, then create new row
                    if (i%4 == 0) {
                        if (tr != null) {
                            document.getElementById('all_lights').appendChild(tr);
                        }
                        tr = null;
                    }

                    light_node = document.createElement('td');
                    light_node.id = 'light_' + light;
                    light_node.setAttribute('data-light', light);
                    light_node.onclick = Lights.Toggle;

                    var light_name = document.createElement('div');
                    light_name.innerText = Tools.UpFirst(light);
                    light_name.className = 'name';
                    light_node.appendChild(light_name);

                    var light_node_state_div = document.createElement('div');
                    light_node_state_img = document.createElement('img');
                    light_node_state_img.id = 'light_' + light + '_state';
                    light_node_state_div.appendChild(light_node_state_img);
                    light_node.appendChild(light_node_state_div);

                    if (tr == null) {
                        tr = document.createElement('tr');
                    }
                    tr.appendChild(light_node);
                } else {
                    light_node_state_img = document.getElementById('light_' + light + '_state');
                }

                // Update light state
                light_node_state_img.alt = result[light]['on'] != null ? (result[light]['on'] ? 'ON' : 'OFF') : '?';
                light_node_state_img.src = Lights.Status2Image(result[light]);
            }
            if (tr != null) {
                document.getElementById('all_lights').appendChild(tr);
            }
        });
    },

    RefreshStatusLoop: function() {
        setTimeout(Lights.RefreshStatusLoop, 300000); // 5 minutes
        Lights.RefreshStatus();
    },

    Initialize: function() {
        setTimeout(Lights.RefreshStatusLoop, 100);
    },

    Status2Image: function(light_status) {
        if (light_status['on'] === null) {
            return 'img/lights/unknown.png';
        } else if (light_status['on']) {
            if (light_status['dimmable'] && light_status['brightness'] <= 50) {
                return 'img/lights/low.png';
            } else if (light_status['dimmable'] && light_status['brightness'] <= 80) {
                return 'img/lights/medium.png';
            } else {
                return 'img/lights/high.png';
            }
        } else {
            return 'img/lights/off.png';
        }
    },

    Toggle: function(click) {
        var click_target = click.target;
        if (click_target.getAttribute('data-light') == null) {
            click_target = click_target.parentElement;
            if (click_target.getAttribute('data-light') == null) {
                click_target = click_target.parentElement;
            }
        }
        var light = click_target.getAttribute('data-light');
        var light_state = document.getElementById('light_' + light + '_state').alt == 'ON';
        window.API.POST('/api/v1/lights/' + light + '/' + (light_state ? 'off' : 'on'), {}, Lights.RefreshStatus);
    },
}
