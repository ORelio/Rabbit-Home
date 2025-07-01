'use strict';

var Weather = {

    Refresh: function() {
        window.API.GET('/api/v1/weather', function(result) {
            document.getElementById('weather_today_image').src = Weather.Description2Image(result.today.description, result.is_day);
            document.getElementById('weather_today_description').innerText = result.today.description;
            document.getElementById('weather_today_minimum').innerText = result.today.minimum.toFixed(0);
            document.getElementById('weather_today_maximum').innerText = result.today.maximum.toFixed(0);
            for (var i = 1; i <= 6; i++) {
                document.getElementById('weather_' + i.toString() + '_day').innerText = Weather.DayOfWeek(i);
                document.getElementById('weather_' + i.toString() + '_image').src = Weather.Description2Image(result.forecast[i].description, true);
                document.getElementById('weather_' + i.toString() + '_minimum').innerText = result.forecast[i].minimum.toFixed(0);
                document.getElementById('weather_' + i.toString() + '_maximum').innerText = result.forecast[i].maximum.toFixed(0);
            }
        });
    },

    Initialize: function() {
        setTimeout(Weather.Refresh, 100);
        setTimeout(Weather.Initialize, 1800000); // 30 minutes
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
            "Pluies orageuses": "storm",
            "Pluie orageuses": "storm",
            "Orages": "storm",
            "Averses orageuses": "storm",
            "Risque d'orages": "storm",
        };
        if (mapping[description] !== undefined) {
            return 'img/weather/' + mapping[description].replace('{dayornight}', is_day ? 'day' : 'night') + '.png';
        } else {
            return 'img/weather/unknown.png';
        }
    },
}
