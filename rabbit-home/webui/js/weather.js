'use strict';

var Weather = {

    Refresh: function() {
        window.API.GET('/api/v1/weather', function(result) {
            document.getElementById('weather_minimum').innerText = result.minimum;
            document.getElementById('weather_current').innerText = result.current;
            document.getElementById('weather_maximum').innerText = result.maximum;
            document.getElementById('weather_refreshed').innerText = Tools.Timestamp2Time(result.refreshed);
        });
    },

    Initialize: function() {
        setTimeout(Weather.Refresh, 100);
        setTimeout(Weather.Initialize, 1800000); // 30 minutes
    },
}
