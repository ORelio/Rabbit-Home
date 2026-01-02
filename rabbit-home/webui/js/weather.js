'use strict';

var Weather = {

    Initialize: function() {
        Tools.ScheduleAutoRefresh(Weather.RefreshForecast, 1800000); // Every 30 minutes
        Tools.ScheduleAutoRefresh(Weather.RefreshSensors);
    },

    RefreshForecast: function() {
        window.API.GET('/api/v1/weather', function(result) {
            if (result.today) {
                document.getElementById('weather_today_image').src = Weather.Description2Image(result.today.description, result.is_day);
                document.getElementById('weather_today_description').innerText = result.today.description;
                document.getElementById('weather_today_minimum').innerText = Weather.RoundedTemperature(result.today.minimum);
                document.getElementById('weather_today_maximum').innerText = Weather.RoundedTemperature(result.today.maximum);
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
                    document.getElementById('weather_' + i.toString() + '_minimum').innerText = Weather.RoundedTemperature(result.forecast[i - 1].minimum);
                    document.getElementById('weather_' + i.toString() + '_maximum').innerText = Weather.RoundedTemperature(result.forecast[i - 1].maximum);
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
        Tools.ApiToTable(window.API.GET, '/api/v1/temperature', 'temperature_sensors', 'temperature_',
            function(item_name, item_data, item_node, initial_build) {
                if (initial_build) {
                    var item_value = document.createElement('div');
                    item_value.id = 'temperature_' + item_name + '_value';
                    item_value.className = 'digits';
                    item_node.appendChild(item_value);

                    var item_time = document.createElement('div');
                    item_time.id = 'temperature_' + item_name + '_time';
                    item_time.className = 'detail refresh_time';
                    item_node.appendChild(item_time);
                }
                document.getElementById('temperature_' + item_name + '_value').innerText = item_data.temperature ? Weather.RoundedTemperature(item_data.temperature, 1) : '--.-';
                document.getElementById('temperature_' + item_name + '_time').innerText = Tools.Timestamp2Time(item_data.time);
            }
        );
    },

    DayOfWeek: function(offset) {
        var weekday = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
        var d = new Date();
        return weekday[(d.getDay() + offset) % 7];
    },

    RoundedTemperature: function(temperature, digits) {
        var rounded = temperature.toFixed(digits === undefined ? 0 : digits);
        return rounded === "-0" ? "0" : rounded;
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
            "Averses de neige faible": "snow-low",
            "Neige forte": "snow",
            "Quelques flocons": "snow-low",
            "Pluie et neige": "rain-snow",
            "Pluie verglaçante": "rain-snow",
            "Brume ou bancs de brouillard": "fog",
            "Bancs de Brouillard": "fog",
            "Brouillard": "fog",
            "Brouillard dense": "fog",
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
