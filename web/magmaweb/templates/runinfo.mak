<div class="x-hidden" id="resultsinfo">
% if run!=None:
<fieldset class="x-fieldset x-fieldset-default">
<legend class="x-fieldset-header x-fieldset-header-default">Description</legend>
<p id="description">${run.description}</p>
</fieldset>
<fieldset class="x-fieldset x-fieldset-default">
<legend class="x-fieldset-header x-fieldset-header-default">MS data options</legend>
<table class='infotable'>
<tr><td>
MS Filename:</td><td> ${run.ms_filename}
</td></tr>
<tr><td>
Maximum MS level:</td><td> ${run.max_ms_level}
</td></tr>
<tr><td>
Absolute intensity threshold for storing peaks in database:</td><td> ${run.abs_peak_cutoff}
</td></tr>
</table>
</fieldset>
<fieldset class="x-fieldset x-fieldset-default">
<legend class="x-fieldset-header x-fieldset-header-default">Generate metabolite options</legend>
<table class='infotable'>
<tr><td>
Maximum number of reaction steps:</td><td> ${run.n_reaction_steps}
</td></tr>
<tr><td>
Metabolism types:</td><td> ${run.metabolism_types}
</td></tr>
</table>
</fieldset>
<fieldset class="x-fieldset x-fieldset-default">
<legend class="x-fieldset-header x-fieldset-header-default">Annotate options</legend>
<table class='infotable'>
<tr><td>
Ionisation mode:</td><td>
% if run.ionisation_mode == 1:
Positive
% else:
Negative
% endif
</td></tr>
<tr><td>
Maximum number bond breaks to generate substructures:</td><td> ${run.max_broken_bonds}
</td></tr>
<tr><td>
Mass precision for matching calculated masses with peaks:</td><td> ${run.mz_precision}
</td></tr>
<tr><td>
Mass precision for matching peaks and precursor ions:</td><td> ${run.precursor_mz_precision}
</td></tr>
<tr><td>
Minimum intensity of level 1 peaks to be annotated:</td><td> ${run.ms_intensity_cutoff}
</td></tr>
<tr><td>
Minimum intensity of fragment peaks to be annotated, as fraction of basepeak:</td><td> ${run.msms_intensity_cutoff}
</td></tr>
<tr><td>
Annotate all level 1 peaks, including those not fragmented:</td><td>
% if run.use_all_peaks:
Yes
% else:
No
% endif
</td></tr>
<tr><td>
Skip substructure annotation of fragment peaks:</td><td>
% if run.skip_fragmentation:
Yes
% else:
No
% endif
</td></tr>
</table>
</fieldset>
% else:
<p id="description">No information, nothing has been done</p>
% endif
</div>