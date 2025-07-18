'use strict';

var Weather = {

    RefreshForecast: function() {
        setTimeout(Weather.RefreshForecast, 1800000); // 30 minutes
        window.API.GET('/api/v1/weather', function(result) {
            if (result.today) {
                document.getElementById('weather_today_image').src = Weather.Description2Image(result.today.description, result.is_day);
                document.getElementById('weather_today_description').innerText = result.today.description;
                document.getElementById('weather_today_minimum').innerText = result.today.minimum.toFixed(0);
                document.getElementById('weather_today_maximum').innerText = result.today.maximum.toFixed(0);
            } else {
                document.getElementById('weather_today_image').src = Weather.Description2Image('UNKNOWN', true);
                document.getElementById('weather_today_description').innerText = 'Attente données';
                document.getElementById('weather_today_minimum').innerText = '--';
                document.getElementById('weather_today_maximum').innerText = '--';
            }
            for (var i = 1; i <= 6; i++) {
                document.getElementById('weather_' + i.toString() + '_day').innerText = Weather.DayOfWeek(i);
                if (result.forecast && i < result.forecast.length) {
                    document.getElementById('weather_' + i.toString() + '_image').src = Weather.Description2Image(result.forecast[i - 1].description, true);
                    document.getElementById('weather_' + i.toString() + '_minimum').innerText = result.forecast[i - 1].minimum.toFixed(0);
                    document.getElementById('weather_' + i.toString() + '_maximum').innerText = result.forecast[i - 1].maximum.toFixed(0);
                } else {
                    document.getElementById('weather_' + i.toString() + '_image').src = Weather.Description2Image('UNKNOWN', true);
                    document.getElementById('weather_' + i.toString() + '_minimum').innerText = '--';
                    document.getElementById('weather_' + i.toString() + '_maximum').innerText = '--';
                }
            }
            document.getElementById('weather_refreshed').innerText = Tools.Timestamp2Time(result.refreshed);
        });
    },

    RefreshSensors: function() {
        setTimeout(Weather.RefreshSensors, 300000); // 5 minutes
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
        setTimeout(Weather.RefreshForecast, 100);
        setTimeout(Weather.RefreshSensors, 100);
    },

    DayOfWeek: function(offset) {
        var weekday = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
        var d = new Date();
        return weekday[(d.getDay() + offset) % 7];
    },

    Description2Image: function(description, is_day) {
        var mapping = {
            "Eclaircies": "{dayornight}/cloud-sun",
            "Peu nuageux": "{dayornight}/sun-cloud",
            "Ensoleillé": "{dayornight}/sun",
            "Ciel clair": "{dayornight}/sun",
            "Ciel voilé": "{dayornight}/sun-cloud",
            "Ciel voilé nuit": "{dayornight}/sun-cloud",
            "Très nuageux": "clouds",
            "Couvert": "cloud",
            "Rares averses": "rain-low",
            "Averses faibles": "rain-low",
            "Averses": "rain-medium",
            "Pluies éparses": "rain-low",
            "Pluie": "rain-medium",
            "Pluie modérée": "rain-medium",
            "Pluie faible": "rain-low",
            "Pluie forte": "rain-high",
            "Risque de grêle": "rain-snow",
            "Risque de grèle": "rain-snow",
            "Bruine / Pluie faible": "rain-drizzle",
            "Bruine": "rain-drizzle",
            "Pluies éparses / Rares averses": "rain-low",
            "Pluie / Averses": "rain-medium",
            "Pluie et neige mêlées": "rain-snow",
            "Neige / Averses de neige": "snow",
            "Neige": "snow",
            "Averses de neige": "snow",
            "Neige forte": "snow",
            "Quelques flocons": "snow-low",
            "Pluie et neige": "rain-snow",
            "Pluie verglaçante": "rain-snow",
            "Brume ou bancs de brouillard": "fog",
            "Bancs de Brouillard": "fog",
            "Brouillard": "fog",
            "Brouillard givrant": "fog-snow",
            "Brume": "fog",
            "Pluies orageuses": "storm-rain",
            "Pluie orageuses": "storm-rain",
            "Orages": "storm",
            "Averses orageuses": "storm-rain",
            "Risque d'orages": "storm",
        };
        if (mapping[description] !== undefined) {
            return 'img/weather/' + mapping[description].replace('{dayornight}', is_day ? 'day' : 'night') + '.png';
        } else {
            return 'img/weather/unknown.png';
        }
    },
}
