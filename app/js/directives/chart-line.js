'use strict';

var directivesModule = require('./_index.js');

var d3 = require('d3');
var nv = require('nvd3');

/**
 * @ngInject
 */
function chartLine() {
  var link = function(scope, el, attrs) {
    var chart = null;

    var svg = d3.select(el[0]).append('svg')
        .attr('width', attrs.width)
        .attr('height', attrs.height);

    var update = function(data) {
      if (typeof data === "undefined") {
        return;
      }

      chart = nv.models.lineChart()
          .margin({ left: 50, right: 50 })
          .useInteractiveGuideline(true);

      chart.tooltip.gravity('s').chartContainer(el[0]);

      chart.xAxis.tickFormat(function(d) { return d3.time.format("%x")(new Date(d)); });

      if (attrs.forcey) {
        chart.forceY(JSON.parse(attrs.forcey));
      }

      svg.datum(data).call(chart);
    };

    scope.$on('windowResize', function() {
      if (chart !== null) {
        chart.update();
      }
    });

    scope.$watch('data', update);
  };

  return {
    restrict: 'EA',
    scope: {
      'data': '=',
      'width': '@',
      'height': '@'
    },
    link: link
  };
}

directivesModule.directive('chartLine', chartLine);