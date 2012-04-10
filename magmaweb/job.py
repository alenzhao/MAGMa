import uuid
import os
import csv
import StringIO
import urllib2
import json

from sqlalchemy import create_engine, and_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import desc, asc, distinct
from sqlalchemy.orm.exc import NoResultFound
from magmaweb.models import Base, Metabolite, Scan, Peak, Fragment, Run

class ScanRequiredError(Exception):
    """ Raised when a scan identifier is required, but non is supplied"""
    pass

class ScanNotFound(Exception):
    """ Raised when a scan identifier is not found"""
    pass

class FragmentNotFound(Exception):
    """ Raised when a fragment is not found"""
    pass

class JobNotFound(Exception):
    """ Raised when a job with a identifier is not found"""
    def __init__(self, jobid):
        self.jobid = jobid

def make_job_factory(params):
    """ Returns JobFactory instance based on params dict

    All keys starting with 'jobfactory.' are used.
    From keys 'jobfactory.' is removed.

    Can be used to create job factory from a config file
    """
    prefix = 'jobfactory.'
    d = {k.replace(prefix, ''):v for k,v in params.iteritems() if k.startswith(prefix)}
    return JobFactory(**d)

class JobQuery(object):
    """ Perform actions on a Job by parsing post params, staging files and building magma cli commands"""
    def __init__(self, id, dir, script='', prestaged=[]):
        self.id = id
        self.dir = dir
        self.script = script
        self.prestaged = prestaged

    def __eq__(self, other):
        return (self.id == other.id and self.dir == other.dir and
            self.script == other.script and self.prestaged == other.prestaged)

    def __repr__(self):
        """Return a printable representation."""
        return "JobQuery({!r}, {!r}, {!r}, {!r})".format(self.id, self.dir, self.script, self.prestaged)

    def add_structures(self, params, has_ms_data=False):
        metsfile = file(os.path.join(self.dir, 'structures.dat'), 'w')
        if (('structures_file' in params) and (params['structures_file'] != '')):
            sf = params['structures_file'].file
            sf.seek(0)
            while 1:
                data = sf.read(2 << 16)
                if not data:
                    break
                metsfile.write(data)
            sf.close()
        else:
            metsfile.write(params['structures'])
        metsfile.close()

        script = "{{magma}} add_structures -t {structure_format} structures.dat {{db}}\n"
        self.script += script.format(structure_format=params['structure_format'])
        self.prestaged.append('structures.dat')

        if ('metabolize' in params):
            self.metabolize(params, has_ms_data)
        else:
            # dont annotate when metabolize is also done
            # as metabolize will call annotate
            if (has_ms_data):
                self.annotate(params)

        return self

    def add_ms_data(self, params, has_metabolites=False):
        msfile = file(os.path.join(self.dir, 'ms_data.dat'), 'w')
        msf = params['ms_data_file'].file
        msf.seek(0)
        while 1:
            data = msf.read(2 << 16)
            if not data:
                break
            msfile.write(data)
        msf.close()
        msfile.close()

        script = "{{magma}} add_ms_data --ms_data_format {ms_data_format} -l {max_ms_level} -a {abs_peak_cutoff} -r {rel_peak_cutoff} --precursor_mz_precision {precursor_mz_precision} ms_data.dat {{db}}\n"
        self.script += script.format(
                               ms_data_format=params['ms_data_format'],
                               max_ms_level=params['max_ms_level'],
                               precursor_mz_precision=params['precursor_mz_precision'],
                               abs_peak_cutoff=params['abs_peak_cutoff'],
                               rel_peak_cutoff=params['rel_peak_cutoff']
                               )
        self.prestaged.append('ms_data.dat')

        if (has_metabolites):
            self.annotate(params)

        return self

    def metabolize(self, params, has_ms_data=False):
        script = "{{magma}} metabolize -s {n_reaction_steps} -m {metabolism_types} {{db}}\n"
        self.script += script.format(
                               n_reaction_steps=params['n_reaction_steps'],
                               metabolism_types=params['metabolism_types']
                               )

        if (has_ms_data):
            self.annotate(params)

        return self

    def metabolize_one(self, params, has_ms_data=False):
        script = "{{magma}} metabolize --metid {metid} -s {n_reaction_steps} -m {metabolism_types} {{db}}\n"
        self.script += script.format(
                               metid=params['metid'],
                               n_reaction_steps=params['n_reaction_steps'],
                               metabolism_types=params['metabolism_types']
                               )

        if (has_ms_data):
            self.annotate(params)

        return self

    def annotate(self, params):
        script = "{{magma}} annotate -p {mz_precision} -c {ms_intensity_cutoff} -d {msms_intensity_cutoff} -i {ionisation_mode} -b {max_broken_bonds} "
        script = script.format(
                               mz_precision=params['mz_precision'],
                               ms_intensity_cutoff=params['ms_intensity_cutoff'],
                               msms_intensity_cutoff=params['msms_intensity_cutoff'],
                               ionisation_mode=params['ionisation_mode'],
                               max_broken_bonds=params['max_broken_bonds']
                               )

        if ('use_all_peaks' in params):
            script += '-u '

        if ('skip_fragmentation' in params):
            script += '-f '

        script += "{db}\n"
        self.script += script

        return self

    def allinone(self, params):
        return self.add_ms_data(params).add_structures(params).metabolize(params).annotate(params)

class JobFactory(object):
    """ Factory which can create jobs """
    def __init__(
                 self, root_dir,
                 init_script='', tarball=None, script_fn='script.sh',
                 db_fn = 'results.db', state_fn = 'job.state',
                 submit_url='http://localhost:9998', time_max=30
                 ):
        """
        root_dir
            Directory in which jobs are created, retrieved

        db_fn
            Sqlite db file name in job directory (default results.db)

        submit_url
            Url of job manager daemon where job can be submitted (default http://localhost:9998)

        script_fn
            Script in job directory which must be run by job manager daemon

        init_script
            String containing os commands to put magma in path, eg. activate virtualenv or unpack tarball

        tarball
            Local absolute location of tarball which contains application which init_script will unpack and run

        state_fn
            Filename where job manager daemon writes job state (default job.state)

        time_max
            Maximum time in minutes a job can take (default 30)
        """
        self.root_dir = root_dir
        self.db_fn = db_fn
        self.submit_url = submit_url
        self.state_fn = state_fn
        self.script_fn = script_fn
        self.tarball = tarball
        self.time_max = time_max
        self.init_script = init_script

    def fromId(self, jobid):
        """
        Finds job db in job root dir.
        Returns a Job instance

        jobid
            Job identifier

        Raises JobNotFound exception when job is not found by jobid
        """
        return Job(jobid,  self._makeJobSession(jobid)(), self.id2jobdir(jobid))

    def _makeJobSession(self, jobid):
        """ Create job db connection """
        engine = create_engine(self.id2url(jobid))
        try:
            engine.connect()
        except OperationalError:
            raise JobNotFound(jobid)
        return sessionmaker(bind=engine)

    def _makeJobDir(self):
        """ Create job dir and returns the job id"""
        jobid = uuid.uuid4()

        # create job dir
        os.makedirs(self.id2jobdir(jobid))
        return jobid

    def fromDb(self, dbfile):
        """
        A job directory is created and the dbfile is copied into it
        Returns a Job instance

        dbfile
            The sqlite result db

        """
        jobid = self._makeJobDir()
        # copy dbfile into job dir
        jobdb = open(self.id2db(jobid), 'wb')
        dbfile.seek(0)
        while 1:
            data = dbfile.read(2 << 16)
            if not data:
                break
            jobdb.write(data)
        jobdb.close()

        return self.fromId(jobid)

    def fromScratch(self):
        """ Creates job from scratch with empty results db """
        jobid = self._makeJobDir()
        session = self._makeJobSession(jobid)()
        Base.metadata.create_all(session.connection())
        return Job(jobid, session, self.id2jobdir(jobid))

    def cloneJob(self, job):
        """ Returns new job which has copy of 'job' db. """
        return self.fromDb(open(self.id2db(job.id)))

    def submitJob2Manager(self, body):
        """ Submits job query to jobmanager daemon

        body is a dict which is submitted as json.

        returns job identifier of job submitted to jobmanager (not the same as job.id).
        """
        request = urllib2.Request(
                                  self.submit_url,
                                  json.dumps(body),
                                  { 'Content-Type': 'application/json' }
                                  )
        # log what is send to job manager
        import logging
        logger = logging.getLogger('magmaweb')
        logger.info(request.data)
        return urllib2.urlopen(request)

    def submitQuery(self, query):
        """
        Writes job script to job dir and submits job to job manager

        query is a JobQuery object

        Returns job identifier
        """

        # write job script into job dir
        script = open(os.path.join(query.dir, self.script_fn), 'w')
        script.write(self.init_script)
        script.write("\n") # hard to add newline in ini file so add it here
        script.write(query.script.format(db=self.db_fn, magma='magma'))
        script.close()

        body = {
                'jobdir': query.dir+'/',
                'executable': "/bin/sh",
                'prestaged': [
                              self.script_fn,
                              self.db_fn
                              ],
                "poststaged": [ self.db_fn ],
                "stderr": "stderr.txt",
                "stdout": "stdout.txt",
                "time_max": self.time_max,
                'arguments': [ self.script_fn ]
                }
        body['prestaged'].extend(query.prestaged)

        if (self.tarball != None):
            body['prestaged'].append(self.tarball)

        self.submitJob2Manager(body)

        return query.id

    def state(self, id):
        """ Returns state of job, see ibis org.gridlab.gat.resources.Job JobState enum for possible states."""
        try:
            jobstatefile = open(os.path.join(self.id2jobdir(id), self.state_fn))
            jobstate = jobstatefile.readline().strip()
            jobstatefile.close()
            return jobstate
        except IOError:
            return 'UNKNOWN'

    def id2jobdir(self, id):
        """ Returns job directory based on id and root_dir """
        return os.path.join(self.root_dir, str(id))

    def id2db(self, id):
        """ Returns sqlite db of job with id """
        return os.path.join(self.id2jobdir(id), self.db_fn)

    def id2url(self, id):
        """ Returns sqlalchemy url of sqlite db of job with id """
        # 3rd / is for username:pw@host which sqlite does not need
        return 'sqlite:///' + self.id2db(id)

class Job(object):
    """
    Job contains results database of Magma calculation run
    """
    def __init__(self, id, session, dir):
        """
        jobid
            A UUID of the job
        session
            Sqlalchemy session to read/write to job db
        dir
            Directory where input and output files reside
        """
        self.id = id
        self.session = session
        self.dir = dir

    def jobquery(self):
        """ Returns JobQuery """
        return JobQuery(self.id, self.dir)

    def maxMSLevel(self):
        """ Returns the maximum nr of MS levels """
        return self.session.query(func.max(Scan.mslevel)).scalar() or 0

    def runInfo(self):
        """ Returns run info"""
        return self.session.query(Run).one()

    def metabolitesTotalCount(self):
        return self.session.query(Metabolite).count()

    def extjsgridfilter(self, q, column, filter):
        """Query helper to convert a extjs grid filter to a sqlalchemy query filter"""
        if (filter['type'] == 'numeric'):
            if (filter['comparison'] == 'eq'):
                return q.filter(column == filter['value'])
            if (filter['comparison'] == 'gt'):
                return q.filter(column > filter['value'])
            if (filter['comparison'] == 'lt'):
                return q.filter(column < filter['value'])
        elif (filter['type'] == 'string'):
            return q.filter(column.contains(filter['value']))
        elif (filter['type'] == 'list'):
            return q.filter(column.in_(filter['value']))
        elif (filter['type'] == 'boolean'):
            return q.filter(column == filter['value'])

    def metabolites(self, start=0, limit=10, sorts=[{"property":"probability", "direction":"DESC"}, {"property":"metid", "direction":"ASC"}], scanid=None, filters=[]):
        """
        Returns dict with total and rows attribute

        start
            Offset
        limit
            Maximum nr of metabolites to return
        scanid
            Only return metabolites that have hits in scan with this identifier. Adds score column.
        filters
            List of dicts which is generated by ExtJS component Ext.ux.grid.FiltersFeature
        sorts
            How to sort metabolites. List of dicts. Eg.
                [{"property":"probability","direction":"DESC"},{"property":"metid","direction":"ASC"}]
        """
        mets = []
        q = self.session.query(Metabolite)

            # custom filters
        fragal = aliased(Fragment)
        if (scanid != None):
            # TODO add score column + order by score
            q = q.add_column(fragal.score).join(fragal.metabolite).filter(
                fragal.parentfragid == 0).filter(fragal.scanid == scanid)

        # add nr_scans column
        stmt = self.session.query(Fragment.metid, func.count(distinct(Fragment.scanid)).label('nr_scans')).filter(
            Fragment.parentfragid == 0).group_by(Fragment.metid).subquery()
        q = q.add_column(stmt.c.nr_scans).outerjoin(stmt, Metabolite.metid == stmt.c.metid)

        for filter in filters:
            # generic filters
            if (filter['field'] == 'nr_scans'):
                col = stmt.c.nr_scans
            elif (filter['field'] == 'score'):
                if (scanid != None):
                    col = fragal.score
                else:
                    raise ScanRequiredError()
            else:
                col = Metabolite.__dict__[filter['field']] #@UndefinedVariable
            q = self.extjsgridfilter(q, col, filter)

        total = q.count()

        for col in sorts:
            if (col['property'] == 'nr_scans'):
                col2 = stmt.c.nr_scans
            elif (col['property'] == 'score'):
                if (scanid != None):
                    col2 = fragal.score
                else:
                    raise ScanRequiredError()
            else:
                col2 = Metabolite.__dict__[col['property']] #@UndefinedVariable
            if (col['direction'] == 'DESC'):
                q = q.order_by(desc(col2))
            elif (col['direction'] == 'ASC'):
                q = q.order_by(asc(col2))

        for r in q[start:(limit + start)]:
            met = r.Metabolite
            row = {
                'metid': met.metid,
                'mol': met.mol,
                'level': met.level,
                'probability': met.probability,
                'reactionsequence': met.reactionsequence,
                'smiles': met.smiles,
                'molformula': met.molformula,
                'isquery': met.isquery,
                'origin': met.origin,
                'nhits': met.nhits,
                'nr_scans': r.nr_scans,
                'mim': met.mim,
                'logp': met.logp
            }
            if ('score' in r.keys()):
                row['score'] = r.score
            mets.append(row)

        return { 'total': total, 'rows': mets }

    def metabolites2csv(self, metabolites):
        """
        Converts array of metabolites to csv file handler

        Params:
        metabolites array like metabolites()['rows']

        Return
        StringIO
        """
        csvstr = StringIO.StringIO()
        headers = [
                   'name', 'smiles', 'probability', 'reactionsequence',
                   'nr_scans', 'molformula', 'mim' , 'isquery', 'logp'
                   ]
        if ('score' in metabolites[0].keys()):
            headers.append('score')

        csvwriter = csv.DictWriter(csvstr, headers, extrasaction='ignore')
        csvwriter.writeheader()
        for m in metabolites:
            m['name'] = m['origin']
            csvwriter.writerow(m)

        return csvstr

    def scansWithMetabolites(self, filters=[], metid=None):
        """Returns id and rt of lvl1 scans which have a fragment in it and for which the filters in params pass

        params:

        metid
            Only return scans that have hits with metabolite with this identifier
        filters
            List which is generated by ExtJS component Ext.ux.grid.FiltersFeature, with columns from Metabolite grid
        """
        fq = self.session.query(Fragment.scanid).filter(Fragment.parentfragid == 0)
        if (metid != None):
            fq = fq.filter(Fragment.metid == metid)
        fq = fq.join(Metabolite)
        for filter in filters:
            if (filter['field'] == 'score'):
                fq = self.extjsgridfilter(fq, Fragment.score, filter)
            elif (filter['field'] != 'nr_scans'):
                fq = self.extjsgridfilter(
                                          fq,
                                          Metabolite.__dict__[filter['field']], #@UndefinedVariable
                                          filter)

        hits = []
        for hit in self.session.query(Scan.rt, Scan.scanid).filter_by(mslevel=1).filter(Scan.scanid.in_(fq)):
            hits.append({
                'id': hit.scanid,
                'rt': hit.rt
            })

        return hits

    def extractedIonChromatogram(self, metid):
        """ Returns extracted ion chromatogram of metabolite with id metid """
        chromatogram = []
        mzq = self.session.query(func.avg(Fragment.mz)).filter(Fragment.metid == metid).filter(Fragment.parentfragid == 0).scalar()
        mzoffset = self.session.query(Run.mz_precision).scalar()
        # fetch max intensity of peaks with mz = mzq+-mzoffset
        for (rt, intens) in self.session.query(Scan.rt, func.max(Peak.intensity)).outerjoin(Peak, and_(Peak.scanid == Scan.scanid, Peak.mz.between(mzq - mzoffset, mzq + mzoffset))).filter(Scan.mslevel == 1).group_by(Scan.rt).order_by(asc(Scan.rt)):
            chromatogram.append({
                'rt': rt,
                'intensity': intens or 0
            })
        return chromatogram

    def chromatogram(self):
        """Returns list of dicts with the id, rt and basepeakintensity for each lvl1 scan"""
        scans = []
        # TODO add left join to find if scan has metabolite hit
        for scan in self.session.query(Scan).filter_by(mslevel=1):
            scans.append({
                'id': scan.scanid,
                'rt': scan.rt,
                'intensity': scan.basepeakintensity
            })

        return scans

    def mspectra(self, scanid, mslevel=None):
        """Returns dict with peaks of a scan

        Also returns the cutoff applied to the scan
        and mslevel, precursor.id (parent scan id) and precursor.mz

        scanid
            Scan identifier of scan of which to return the mspectra

        mslevel
            Ms level on which the scan must be. Optional.
            If scanid not on mslevel raises ScanNotFound

        """
        scanq = self.session.query(Scan).filter(Scan.scanid == scanid)
        if (mslevel != None):
            scanq = scanq.filter(Scan.mslevel == mslevel)

        try:
            scan = scanq.one()
        except NoResultFound:
            raise ScanNotFound()

        # lvl1 scans use absolute cutoff, lvl>1 use ratio of basepeak as cutoff
        if (scan.mslevel == 1):
            cutoff = self.session.query(Run.ms_intensity_cutoff).scalar()
        else:
            cutoff = self.session.query(Scan.basepeakintensity * Run.msms_intensity_cutoff).filter(Scan.scanid == scanid).scalar()

        peaks = []
        for peak in self.session.query(Peak).filter_by(scanid=scanid):
            peaks.append({
                'mz': peak.mz,
                'intensity': peak.intensity
            })

        return { 'peaks': peaks, 'cutoff': cutoff, 'mslevel': scan.mslevel, 'precursor': { 'id': scan.precursorscanid, 'mz': scan.precursormz } }

    def fragments(self, scanid, metid, node=''):
        """Returns dict with metabolites and its lvl2 fragments when node is not set
        When node is set then returns the children fragments as list which have node as parent fragment

        Can be used in a Extjs.data.TreeStore if jsonified.

        scanid
            Fragments on scan with this identifier

        metid
            Fragments of metabolite with this identifier

        node
            The fragment identifier to fetch children fragments for. Optional.

        Raises FragmentNotFound when no fragment is found with scanid/metid combination
        """
        def q():
            return self.session.query(Fragment, Metabolite.mol, Scan.mslevel).join(Metabolite).join(Scan)

        def fragment2json(row):
            (frag, mol, mslevel) = row
            f = {
                'fragid': frag.fragid,
                'scanid': frag.scanid,
                'metid': frag.metid,
                'score': frag.score,
                'mol': mol,
                'atoms': frag.atoms,
                'mz': frag.mz,
                'mass': frag.mass,
                'deltah': frag.deltah,
                'mslevel': mslevel,
            }
            if (len(frag.children) > 0):
                f['expanded'] = False
                f['leaf'] = False
            else:
                f['expanded'] = True
                f['leaf'] = True
            return f

        # parent metabolite
        if (node == ''):
            structures = []
            for row in q().filter(
                                  Fragment.scanid == scanid
                         ).filter(
                                  Fragment.metid == metid
                         ).filter(
                                  Fragment.parentfragid == 0
                         ):
                structure = fragment2json(row)
                structure['children'] = []
                for frow in q().filter(Fragment.parentfragid == structure['fragid']):
                    structure['expanded'] = True
                    structure['children'].append(fragment2json(frow))
                structures.append(structure)

            if (len(structures) == 0):
                raise FragmentNotFound()
            return { 'children': structures, 'expanded': True}
        # fragments
        else:
            fragments = []
            for row in q().filter(Fragment.parentfragid == node):
                fragments.append(fragment2json(row))
            return fragments

    def stderr(self):
        """Returns stderr text file"""
        return open(os.path.join(self.dir, 'stderr.txt'), 'rb')
