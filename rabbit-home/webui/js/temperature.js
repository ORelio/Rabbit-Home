'use strict';

var Temperature = {

    Refresh: function() {
        window.API.GET('/api/v1/temperature', function(result) {
            var sensors = Object.keys(result);
            for (var i=0; i < sensors.length; i++) {
                var sensor = sensors[i];

                // Create node in list if not present yet
                if (document.getElementById('temperature_' + sensor + '_value') === null) {
                    var td = document.createElement('td');
                    td.style["width"] = (100 / sensors.length).toString() + '%';

                    var span_name = document.createElement('div');
                    span_name.innerText = Tools.UpFirst(sensor);
                    span_name.className = 'name';
                    td.appendChild(span_name);

                    var span_value = document.createElement('div');
                    span_value.id = 'temperature_' + sensor + '_value';
                    span_value.className = 'digits';
                    td.appendChild(span_value);

                    var span_time = document.createElement('div');
                    span_time.id = 'temperature_' + sensor + '_time';
                    span_time.className = 'refresh_time';
                    td.appendChild(span_time);

                    document.getElementById('temperature_sensors').appendChild(td);
                }

                document.getElementById('temperature_' + sensor + '_value').innerText = result[sensor].temperature ? result[sensor].temperature.toFixed(1) : '--.-';
                document.getElementById('temperature_' + sensor + '_time').innerText = Tools.Timestamp2Time(result[sensor].time);
            }
        });
    },

    Initialize: function() {
        setTimeout(Temperature.Refresh, 100);
        setTimeout(Temperature.Initialize, 300000); // 5 minutes
    },
}
