import rdkit_engine as Chem
import numpy
cimport numpy

# ctypedef Chem.rdchem.Mol rdkit_mol


typew={"AROMATIC":3.0,\
       "DOUBLE":2.0,\
       "TRIPLE":3.0,\
       "SINGLE":1.0}
ringw={False:1,True:1}
heterow={False:2,True:1}
cdef int missingfragmentpenalty=10


mims={1:1.0078250321,\
      6:12.0000000,\
      7:14.0030740052,\
      8:15.9949146221,\
      9:18.99840320,\
      15:30.97376151,\
      16:31.97207069,\
      17:34.96885271,\
      35:78.9183376,\
      53:126.904468}

Hmass=mims[1]     # Mass of hydrogen atom

ctypedef struct bonded_atom:
    int nbonds
    int[8] atoms

ctypedef struct bond_breaks_score_pair:
    int breaks
    float score

cdef class FragmentEngine(object):

    cdef unsigned long long new_fragment,template_fragment,frag
    cdef int max_broken_bonds,max_small_losses,natoms
    cdef bonded_atom[64] bonded_atoms
    cdef float[64] atom_masses
    cdef list neutral_loss_atoms
    cdef set all_fragments,total_fragments,current_fragments,new_fragments
    cdef int nbonds
    cdef unsigned long long[128] bonds
    cdef float[128] bondscore
    cdef numpy.ndarray fragment_masses,fragments,bondbreaks,scores
    #cdef rdkit_mol mol
    
    def __init__(self,structure,max_broken_bonds,max_small_losses):
        mol=Chem.MolFromMolBlock(str(structure.mol))
        self.natoms=Chem.natoms(mol)  # number of atoms in the molecule
        if self.natoms<=64:
            self.max_broken_bonds=max_broken_bonds
            self.max_small_losses=max_small_losses
            self.nbonds=Chem.nbonds(mol)
            self.neutral_loss_atoms=[]
            # self.atom_masses=[]
            # self.bonded_atoms=[]           # [[list of atom numbers]]
            # self.bonds=set([])
            # self.bondscore={}
            self.new_fragment=0
            self.template_fragment=0
            self.fragment_masses=numpy.zeros((max_broken_bonds+max_small_losses)*2+3)
            self.fragments=numpy.array([0])
            self.bondbreaks=numpy.array([0])
            self.scores=numpy.array([0.0])
            # self.avg_score=None
            frag=(1<<self.natoms)-1
    
            for x in range(self.natoms):
                self.bonded_atoms[x].nbonds=0
                self.atom_masses[x]=Chem.GetExtendedAtomMass(mol,x)
                if Chem.GetAtomSymbol(mol,x) == 'O' and Chem.GetAtomHs(mol,x) == 1:
                    self.neutral_loss_atoms.append(x)
            for x in range(self.nbonds):
                a1,a2 = Chem.GetBondAtoms(mol,x)
                self.bonded_atoms[a1].atoms[self.bonded_atoms[a1].nbonds]=a2
                self.bonded_atoms[a1].nbonds+=1
                self.bonded_atoms[a2].atoms[self.bonded_atoms[a2].nbonds]=a1
                self.bonded_atoms[a2].nbonds+=1
                bond = (1<<a1) | (1<<a2)
                bondscore = typew[Chem.GetBondType(mol,x)]*heterow[Chem.GetAtomSymbol(mol,a1) != 'C' or Chem.GetAtomSymbol(mol,a2) != 'C']
                self.bonds[x]=bond
                self.bondscore[x]=bondscore
                
            self.all_fragments=set([frag])
            self.total_fragments=set([frag])
            self.current_fragments=set([frag])
            self.new_fragments=set([frag])
            self.add_fragment(frag,self.calc_fragment_mass(frag),0,0)
    
    cdef void extend(self,int atom):
        cdef int a,bonded_a
        cdef unsigned long long atombit
        for a in range(self.bonded_atoms[atom].nbonds):
            bonded_a=self.bonded_atoms[atom].atoms[a]
            atombit=1<<bonded_a
            if atombit & self.template_fragment and not atombit & self.new_fragment:
                self.new_fragment = self.new_fragment | atombit
                self.extend(bonded_a)

    def generate_fragments(self):
        # generate fragments
        cdef unsigned long long fragment,frag
        cdef int atom,a,bonded_a
        cdef bond_breaks_score_pair bbsp

        for step in range(self.max_broken_bonds):                    # perform fragmentation for nstep steps
            for fragment in self.current_fragments:   # loop of all fragments to be fragmented
                for atom in range(self.natoms):       # loop of all atoms
                    if (1<<atom) & fragment:            # in the fragment
                        self.template_fragment=fragment^(1<<atom) # remove the atom
                        list_ext_atoms=set([])
                        extended_fragments=set([])
                        for a in range(self.bonded_atoms[atom].nbonds):              # find all its bonded atoms
                            bonded_a=self.bonded_atoms[atom].atoms[a]
                            if (1<<bonded_a) & self.template_fragment:        # present in the fragment
                                list_ext_atoms.add(bonded_a)
                        if len(list_ext_atoms)==1:                         # in case of one bonded atom, the new fragment
                            extended_fragments.add(self.template_fragment) # is the remainder of the old fragment
                        else:
                            for a in list_ext_atoms:                # otherwise extend all atoms
                                for frag in extended_fragments:     # except when deleted atom is in a ring
                                    if (1<<a) & frag:               # -> previous extended fragment contains
                                        break                       #    already the ext_atom, calculate fragment only once
                                else:
                                    self.new_fragment=1<<a          # extend atom
                                    self.extend(a)
                                    extended_fragments.add(self.new_fragment)
                        for frag in extended_fragments:
                            if frag not in self.all_fragments:   # add extended fragments if not yet present
                                self.all_fragments.add(frag)     # to the collection
                                bbsp=self.score_fragment(frag)
                                if bbsp.breaks<=self.max_broken_bonds and bbsp.score < (missingfragmentpenalty+5):
                                    self.new_fragments.add(frag)
                                    self.total_fragments.add(frag)
                                    self.add_fragment(frag,self.calc_fragment_mass(frag),bbsp.score,bbsp.breaks)
            self.current_fragments=self.new_fragments
            self.new_fragments=set([])
        for step in range(self.max_small_losses):                    # number of OH losses
            for fragment in self.current_fragments:   # loop of all fragments on which to apply neutral loss rules
                for atom in self.neutral_loss_atoms:       # loop of all atoms
                    if (1<<atom) & fragment:            # in the fragment
                        frag=fragment^(1<<atom)
                        if frag not in self.total_fragments:   # add extended fragments if not yet present
                            self.total_fragments.add(frag)     # to the collection
                            bbsp=self.score_fragment(frag)
                            if bbsp.score < (missingfragmentpenalty+5):
                                self.new_fragments.add(frag)
                                self.add_fragment(frag,self.calc_fragment_mass(frag),bbsp.score,bbsp.breaks)
            self.current_fragments=self.new_fragments
            self.new_fragments=set([])
        print 'Fragments generated -->',len(self.fragments)

        # calculate masses and scores for fragments
        # first items fragment_masses and fragment_info represent the complete molecule
        # self.calc_avg_score()

    cdef bond_breaks_score_pair score_fragment(self,unsigned long long fragment):
        cdef int b,bondbreaks
        cdef unsigned long long bond
        cdef float score
        cdef bond_breaks_score_pair bbsp
        score=0
        bondbreaks=0
        for b in range(self.nbonds):
            bond=self.bonds[b]
            if 0 < (fragment & bond) < bond:
                score+=self.bondscore[b]
                bondbreaks+=1
        bbsp.breaks=bondbreaks
        bbsp.score=score
        #if score==0:
        #    print "score=0: ",fragment,bondbreaks
        return bbsp

    def score_fragment_rel2parent(self,unsigned long long fragment,unsigned long long parent):
        cdef int b
        cdef unsigned long long bond
        cdef float score
        score=0
        for b in range(self.nbonds):
            bond=self.bonds[b]
            if 0 < (fragment & bond) < (bond & parent):
                score+=self.bondscore[b]
        return score
    
    cdef float calc_fragment_mass(self, unsigned long long fragment):
        cdef int atom
        cdef float fragment_mass=0.0
        for atom in range(self.natoms):
            if fragment & (1<<atom):
                fragment_mass+=self.atom_masses[atom]
        return fragment_mass

    def add_fragment(self,fragment,fragmentmass,score,bondbreaks):
        self.fragment_masses = numpy.vstack((self.fragment_masses,
                       numpy.hstack((numpy.zeros(self.max_broken_bonds+self.max_small_losses-bondbreaks),
                                  numpy.arange(-bondbreaks-1,bondbreaks+2)*Hmass+fragmentmass,
                                  numpy.zeros(self.max_broken_bonds+self.max_small_losses-bondbreaks)
                                  ))
                       ))
        # self.info.append([fragment,score,bondbreaks])
        self.fragments = numpy.hstack((self.fragments,numpy.array([fragment])))
        self.bondbreaks = numpy.hstack((self.bondbreaks,numpy.array([bondbreaks])))
        self.scores = numpy.hstack((self.scores,numpy.array([score])))

    def calc_avg_score(self):
        # self.avg_score = sum([i[1] for i in self.info])/len(self.info)
        self.avg_score = numpy.average(self.scores)

    def get_avg_score(self):
        return self.avg_score

    def find_fragments(self,mass,parent,precision,mz_precision_abs):
        cdef int i
        result=numpy.where(numpy.where(self.fragment_masses < max(mass*precision,mass+mz_precision_abs),
                                 self.fragment_masses,0) > min(mass/precision,mass-mz_precision_abs))
        fragment_set=[]
        for i in range(len(result[0])):
            fid=result[0][i]
            fragment_set.append([self.fragments[fid],
                                 self.scores[fid],
                                 self.bondbreaks[fid],
                                 self.fragment_masses[fid][self.max_broken_bonds+self.max_small_losses+1],
                                 self.max_broken_bonds+self.max_small_losses+1-result[1][i]
                                 ])
        return fragment_set
    
    def get_fragment_info(self,unsigned long long fragment):
        cdef int atom
        atomstring=""
        atomlist=[]
        for atom in range(self.natoms):
            if ((1<<atom) & fragment):
                atomstring+=','+str(atom)
                atomlist.append(atom)
        return atomstring,atomlist
    
    def get_natoms(self):
        return self.natoms
    
    def accepted(self):
        return (self.natoms<=64)