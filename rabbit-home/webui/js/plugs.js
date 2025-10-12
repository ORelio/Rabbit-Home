'use strict';

var Plugs = {

    RefreshStatus: function() {
        window.API.GET('/api/v1/plugs', function(result) {
            var plugs = Object.keys(result);
            var tr = null;
            for (var i=0; i < plugs.length; i++) {
                var plug = plugs[i];

                var plug_node = document.getElementById('plug_' + plug);
                var plug_node_state_img = null;

                // Create node in list if not present yet
                if (plug_node === null) {

                    //Add at most 4 elements per row, then create new row
                    if (i%4 == 0) {
                        if (tr != null) {
                            document.getElementById('all_plugs').appendChild(tr);
                        }
                        tr = null;
                    }

                    plug_node = document.createElement('td');
                    plug_node.id = 'plug_' + plug;
                    plug_node.setAttribute('data-plug', plug);
                    plug_node.onclick = Plugs.Toggle;

                    var plug_name = document.createElement('div');
                    plug_name.innerText = Tools.UpFirst(plug);
                    plug_name.className = 'name';
                    plug_node.appendChild(plug_name);

                    var plug_node_state_div = document.createElement('div');
                    plug_node_state_img = document.createElement('img');
                    plug_node_state_img.id = 'plug_' + plug + '_state';
                    plug_node_state_div.appendChild(plug_node_state_img);
                    plug_node.appendChild(plug_node_state_div);

                    if (tr == null) {
                        tr = document.createElement('tr');
                    }
                    tr.appendChild(plug_node);
                } else {
                    plug_node_state_img = document.getElementById('plug_' + plug + '_state');
                }

                // Update plug state
                plug_node_state_img.alt = result[plug] != null ? (result[plug] ? 'ON' : 'OFF') : '?';
                plug_node_state_img.src = Plugs.Status2Image(result[plug]);
            }
            if (tr != null) {
                document.getElementById('all_plugs').appendChild(tr);
            }
        });
    },

    RefreshStatusLoop: function() {
        setTimeout(Plugs.RefreshStatusLoop, 300000); // 5 minutes
        Plugs.RefreshStatus();
    },

    Initialize: function() {
        setTimeout(Plugs.RefreshStatusLoop, 100);
    },

    Status2Image: function(plug_status) {
        if (plug_status === null) {
            return 'img/plugs/unknown.png';
        } else if (plug_status) {
            return 'img/plugs/on.png';
        } else {
            return 'img/plugs/off.png';
        }
    },

    Toggle: function(click) {
        var click_target = click.target;
        if (click_target.getAttribute('data-plug') == null) {
            click_target = click_target.parentElement;
            if (click_target.getAttribute('data-plug') == null) {
                click_target = click_target.parentElement;
            }
        }
        var plug = click_target.getAttribute('data-plug');
        var plug_state = document.getElementById('plug_' + plug + '_state').alt == 'ON';
        window.API.POST('/api/v1/plugs/' + plug + '/' + (plug_state ? 'off' : 'on'), {}, Plugs.RefreshStatus);
    },
}
