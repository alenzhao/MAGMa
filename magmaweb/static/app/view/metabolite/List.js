/**
 * Grid of metabolites.
 * @author <a href="mailto:s.verhoeven@esciencecenter.nl">Stefan Verhoeven</a>
 */
Ext.define('Esc.magmaweb.view.metabolite.List', {
  extend: 'Ext.grid.Panel',
  alias: 'widget.metabolitelist',
  requires: [
    'Ext.ux.grid.FiltersFeature', 'Esc.chemdoodle.Column',
    'Ext.toolbar.Paging', 'Ext.grid.column.Boolean',
    'Ext.grid.column.Action', 'Ext.selection.CheckboxModel'
  ],
  store: 'Metabolites',
  viewConfig: {
    emptyText: 'No structures available: Add structures or relax filters'
  },
  selType: 'checkboxmodel',
  selModel: {
    allowDeselect: true,
    mode: 'SINGLE'
  },
  dockedItems: [{
    xtype: 'pagingtoolbar',
    store: 'Metabolites',   // same store GridPanel is using
    dock: 'bottom',
    displayInfo: true,
    items: [{
      xtype: 'combo',
      width: 170,
      store: [
        [10, '10 metabolites per page'],
        [25, '25 metabolites per page'],
        [50, '50 metabolites per page'],
        [100, '100 metabolites per page'],
        [250, '250 metabolites per page'],
        [500, '500 metabolites per page'],
        [1000, '1000 metabolites per page']
      ],
      forceSelection: true,
      triggerAction: 'all',
      action: 'pagesize'
    }]
  }],
  initComponent: function() {
    console.log('Init met grid');
    var me = this;
    var molcol = Ext.create('Esc.chemdoodle.Column', {
      text: 'Molecule', dataIndex: 'mol',
      width: 162
    });

    var mfilters = Ext.create('Ext.ux.grid.FiltersFeature',{
      id: 'mfilter',
      encode: true
    });

    this.addEvents([
        /**
         * @event metabolize
         * Fired after metabolize column action is clicked
         * @param {Ext.data.Model} record The record to metabolize
         */
        'metabolize'
    ]);

    Ext.apply(this, {
      columns: [
        {text: 'ID', dataIndex: 'metid', hidden: true},
        molcol,
        {text: 'Level', dataIndex: 'level', filter: { type: 'list',  options: ['0','1','2','3'] }, hidden:true},
        {text: 'Probability', dataIndex: 'probability', filter: { type: 'numeric' }},
        {text: 'Reaction seq.', dataIndex: 'reactionsequence', flex:1, filter: { type: 'string' }, renderer: function(v) {
          return '<ol><li>'+v.replace("\n","</li><li>")+'</li></ol>';
        }},
        {text: 'Scans', dataIndex: 'nr_scans', filter: { type: 'numeric'
            , value:{gt:0}, active: true
        }},
        {text: 'Smile', dataIndex: 'smiles', hidden:true},
        {text: 'Formula', dataIndex: 'molformula', filter: { type: 'string' }},
        {text: 'Monoisotopic mass', dataIndex: 'mim', filter: { type: 'numeric' }, hidden: true},
        {text: 'Query', dataIndex: 'isquery', xtype:'booleancolumn', trueText:'Yes', falseText:'No', filter: { type: 'boolean' }},
        {text: 'Name', dataIndex: 'origin', hidden: true, filter: { type: 'string' }},
        {text: 'Fragment score', dataIndex: 'score', hidden: true, filter: { type: 'numeric' }},
        {text: 'LogP', dataIndex: 'logp', filter: { type: 'numeric' }, hidden: true},
        {xtype: 'actioncolumn', width:30, text:'Commands',
            items: [{
                tooltip: 'Metabolize',
                iconCls: 'metabolize-col',
                handler: function(grid, rowIndex) {
                    me.fireEvent('metabolize', me.getStore().getAt(rowIndex));
                }
            }]
        }
      ],
      plugins: [molcol],
      features: [mfilters]
    });
    this.callParent(arguments);
  },
  /**
   * Clears all filters applied to metabolites
   */
  clearFilters: function() {
    this.getView().getFeature('mfilter').clearFilters();
  },
  /**
   * Get column with scores.
   *
   * Column should only be shown when a scan has been selected.
   *
   * @return {Ext.grid.column.Column}
   */
  getFragmentScoreColumn: function() {
      return this.columns.filter(function(c) { return (c.dataIndex == "score")})[0];
  },
  /**
   * Get column with commands.
   *
   * @return {Ext.grid.column.Action}
   */
  getCommandsColumn: function() {
      return this.columns.filter(function(c) { return (c.text == "Commands")})[0];
  },
  /**
   * Hides column with scores.
   */
  hideFragmentScoreColumn: function() {
    this.getFragmentScoreColumn().hide();
  },
  /**
   * Shows column with scores.
   */
  showFragmentScoreColumn: function() {
    this.getFragmentScoreColumn().show();
  }
});
