import nest
import numpy as np
from scipy.optimize import fmin
import time
from copy import deepcopy
import sys
import default
from scipy.sparse import csr_matrix
import pylab
#from Helper import GeneralHelper
small = 1e-10


def max_PSP_exp(tau_m, tau_syn, C_m=1., E_l=0.):
    tmax = np.log(tau_syn / tau_m) / (1 / tau_m - 1 / tau_syn)
    print('tmax', tmax)
    B = tau_m * tau_syn / C_m / (tau_syn - tau_m)
    return (E_l - B) * np.exp(-tmax / tau_m) + B * np.exp(-tmax / tau_syn)
    """calculates the maximum psp amplitude for exponential synapses and unit J"""


def calc_js(params):
    if params.get('mazzucato_js', False):
        # weights from mazzucato et al 2015
        js = np.array([[1.77, -3.18], [1.06, -4.24]])
        print(('mazzucato! ', js))
        return js
    # excitatory units
    N_E = params.get('N_E', default.N_E)
    # inhibitory units
    N_I = params.get('N_I', default.N_I)
    N = N_E + N_I   # total units
    ps = params.get('ps', default.ps)  # connection probs
    ge = params.get('ge', default.ge)
    gi = params.get('gi', default.gi)
    gie = params.get('gie', default.gie)
    V_th_E = params.get('V_th_E', default.V_th_E)   # threshold voltage
    V_th_I = params.get('V_th_I', default.V_th_I)
    print(('calcJS V_th', V_th_E, V_th_I))
    tau_E = params.get('tau_E', default.tau_E)
    tau_I = params.get('tau_I', default.tau_I)
    E_L = params.get('E_L', default.E_L)
    neuron_type = params.get('neuron_type', default.neuron_type)
    if 'iaf_psc_exp' in neuron_type:
        tau_syn_ex = params.get('tau_syn_ex', default.tau_syn_ex)
        tau_syn_in = params.get('tau_syn_in', default.tau_syn_in)
        amp_EE = max_PSP_exp(tau_E, tau_syn_ex)
        amp_EI = max_PSP_exp(tau_E, tau_syn_in)
        amp_IE = max_PSP_exp(tau_I, tau_syn_ex)
        amp_II = max_PSP_exp(tau_I, tau_syn_in)

    else:
        amp_EE = 1.
        amp_EI = 1.
        amp_IE = 1.
        amp_II = 1.

    js = np.zeros((2, 2))
    K_EE = N_E * ps[0, 0]
    js[0, 0] = (V_th_E - E_L) * (K_EE**-0.5) * N**0.5 / amp_EE
    js[0, 1] = -ge * js[0, 0] * ps[0, 0] * \
        N_E * amp_EE / (ps[0, 1] * N_I * amp_EI)
    K_IE = N_E * ps[1, 0]
    js[1, 0] = gie * (V_th_I - E_L) * (K_IE**-0.5) * N**0.5 / amp_IE
    js[1, 1] = -gi * js[1, 0] * ps[1, 0] * \
        N_E * amp_IE / (ps[1, 1] * N_I * amp_II)

    # print js
    return js


def FPT(tau_m, E_L, I_e, C_m, Vtarget, Vstart):
    """ calculate first pasage time between Vstart and Vtarget."""
    return -tau_m * np.log((Vtarget - E_L - tau_m * I_e / C_m) / (Vstart - E_L - tau_m * I_e / C_m + small))


def V_FPT(tau_m, E_L, I_e, C_m, Ttarget, Vtarget, t_ref):
    """ calculate the initial voltage required to obtain a certain first passage time. """
    return (Vtarget - E_L - tau_m * I_e / C_m) * np.exp((Ttarget) / tau_m) + E_L + tau_m * I_e / C_m


def simulate(params):
    startbuild = time.time()
    nest.ResetKernel()
    nest.set_verbosity('M_WARNING')

    randseed = params.get('randseed', np.random.randint(1000000))
    print(('randseed', randseed))
    # simulation parameters
    dt = params.get('dt', 0.1)   # integration time step
    simtime = params.get('simtime', 1000.)  # simulation time
    warmup = params.get('warmup', 0)
    record_voltage = params.get('record_voltage', False)
    record_from = params.get('record_from', 'all')
    recording_interval = params.get('recording_interval', dt)
    return_weights = params.get('return_weights', False)
    n_jobs = params.get('n_jobs', 1)

    # stimulation
    # clusters to be stimulated
    stim_clusters = params.get('stim_clusters', None)
    # amplitude of the stimulation current in pA
    stim_amp = params.get('stim_amp', 0.)
    # list of stimulation start times
    stim_starts = params.get('stim_starts', [])
    # list of stimulation end times
    stim_ends = params.get('stim_ends', [])

    # multiple stimulations
    multi_stim_clusters = params.get('multi_stim_clusters', None)
    multi_stim_amps = params.get('multi_stim_amps', [])
    multi_stim_times = params.get('multi_stim_times', [])

    # network parameters
    # excitatory units
    N_E = params.get('N_E', default.N_E)
    # inhibitory units
    N_I = params.get('N_I', default.N_I)
    N = N_E + N_I                                                  # total units

    # connectivity parameters
    ps = params.get('ps', default.ps)  # connection probs
    js = params.get('js', default.js)           # connection weights
    ge = params.get('ge', default.ge)
    # relative strength of inhibition
    gi = params.get('gi', default.gi)
    # number of clusters
    Q = params.get('Q', default.Q)
    # number of combined inhibitory clusters
    portion_I = params.get('portion_I', 1)
    # intra-cluster weight factors
    jplus = params.get('jplus', default.jplus)
    # if True, the J- from Mazzucato2015 is used
    mazzucato_jminus = params.get('mazzucato_jminus', False)
    # gamma parameter in Mazzucatos J- formulation
    gamma = params.get('gamma', 0.5)
    # synaptic delay
    delay = params.get('delay', default.delay)
    # scale factor applied to js
    s = params.get('s', default.s)
    # make sure number of clusters and units are compatible
    # assert N_E%Q == 0, 'N_E needs to be evenly divisible by Q'
    # assert N_I%Q == 0, 'N_I needs to be evenly divisible by Q'
    # units per cluster
    cluster_units_E = int(N_E) // int(Q)
    background_units_E = N_E - Q * cluster_units_E
    # cluster_units_I = int(N_I) / int(Q)
    # background_units_I = N_I - Q * cluster_units_I
    cluster_units_I = int(N_I) // (int(Q) / int(portion_I))
    background_units_I = N_I - int((Q/float(portion_I)) * cluster_units_I)

    fixed_indegree = params.get('fixed_indegree', default.fixed_indegree)

    # neuron parameters
    neuron_type = params.get('neuron_type', default.neuron_type)
    E_L = params.get('E_L', default.E_L)          # resting potential
    C_m = params.get('C_m', default.C_m)          # membrane capacitance
    # excitatory membrane time constant
    tau_E = params.get('tau_E', default.tau_E)
    # inhibitory membrane time constant
    tau_I = params.get('tau_I', default.tau_I)
    t_ref = params.get('t_ref', default.t_ref)      # refractory period
    V_th_E = params.get('V_th_E', default.V_th_E)   # threshold voltage
    V_th_I = params.get('V_th_I', default.V_th_E)
    V_r = params.get('V_r', default.V_r)          # reset voltage
    I_th_E = params.get('I_th_E', default.I_th_E)
    if I_th_E is None:
        I_xE = params.get('I_xE', default.I_xE)
    else:
        I_xE = I_th_E * (V_th_E - E_L) / tau_E * C_m

    I_th_I = params.get('I_th_I', default.I_th_I)
    if I_th_I is None:
        I_xI = params.get('I_xI', default.I_xI)
    else:
        I_xI = I_th_I * (V_th_I - E_L) / tau_I * C_m
    # print I_xE,I_xI
    delta_I_xE = params.get('delta_I_xE', default.delta_I_xE)
    delta_I_xI = params.get('delta_I_xI', default.delta_I_xI)

    V_m = params.get('V_m', default.V_m)

    E_neuron_params = {'E_L': E_L, 'C_m': C_m, 'tau_m': tau_E,
                       't_ref': t_ref, 'V_th': V_th_E, 'V_reset': V_r, 'I_e': I_xE}
    I_neuron_params = {'E_L': E_L, 'C_m': C_m, 'tau_m': tau_I,
                       't_ref': t_ref, 'V_th': V_th_I, 'V_reset': V_r, 'I_e': I_xI}
    if 'iaf_psc_exp' in neuron_type:
        tau_syn_ex = params.get('tau_syn_ex', default.tau_syn_ex)
        tau_syn_in = params.get('tau_syn_in', default.tau_syn_in)
        E_neuron_params['tau_syn_ex'] = tau_syn_ex
        E_neuron_params['tau_syn_in'] = tau_syn_in
        I_neuron_params['tau_syn_in'] = tau_syn_in
        I_neuron_params['tau_syn_ex'] = tau_syn_ex

    # if js are not given compute them so that sqrt(K) spikes equal v_thr-E_L and rows are balanced
    if np.isnan(js).any():
        js = calc_js(params)
    js *= s

    # print (js/np.sqrt(N))
    # print(GeneralHelper.mergeParams(params, default))

    # jminus is calculated so that row sums remain constant
    if Q > 1:
        if mazzucato_jminus:
            f = Q * cluster_units_E / float(N_E)
            jminus = 1 - f * gamma / Q * (jplus - 1)
            print(('mazzucato_jminus! ', jminus, (Q - jplus) / float(Q - 1)))
        else:
            jplus = np.minimum(jplus, Q)
            jminus = (Q - jplus) / float(Q - 1)
    else:
        jplus = np.ones((2, 2))
        jminus = np.ones((2, 2))

    # offgrid_spiking ?

    np.random.seed(randseed)
    randseeds = list(range(randseed + 2, randseed + 2 + n_jobs))
    print('v',randseeds)
    print('v',n_jobs)
    nest.SetKernelStatus({"resolution": dt,
                          "print_time": True, "overwrite_files": True,
                          'local_num_threads': n_jobs,
                          'grng_seed': randseed + 1,
                          'rng_seeds': randseeds})
    print("Building network")

    # create the neuron populations
    E_pops = []
    I_pops = []
    for q in range(Q):
        E_pops.append(nest.Create(neuron_type, int(cluster_units_E)))
        nest.SetStatus(E_pops[-1], [E_neuron_params])
    if background_units_E > 0:
        E_pops.append(nest.Create(neuron_type, int(background_units_E)))
        nest.SetStatus(E_pops[-1], [E_neuron_params])

    # for q in range(Q):
    #     I_pops.append(nest.Create(neuron_type, N_I / Q))
    #     nest.SetStatus(I_pops[-1], [I_neuron_params])
    # if background_units_I > 0:
    #     I_pops.append(nest.Create(neuron_type, background_units_I))
    #     nest.SetStatus(I_pops[-1], [I_neuron_params])

    for q in range(int(Q/portion_I)):
        I_pops.append(nest.Create(neuron_type, int(cluster_units_I)))
        nest.SetStatus(I_pops[-1], [I_neuron_params])
    
    if background_units_I > 0:
        print("!!!!!back_units_I more than 0!!!!!!!")
        I_pops.append(nest.Create(neuron_type, int(background_units_I)))
        nest.SetStatus(I_pops[-1], [I_neuron_params])

    if delta_I_xE > 0:
        for E_pop in E_pops:
            I_xEs = nest.GetStatus(E_pop, 'I_e')
            nest.SetStatus(E_pop, [{'I_e': (
                1 - 0.5 * delta_I_xE +
                np.random.rand() * delta_I_xE) * ixe} for ixe in I_xEs])

    if delta_I_xI > 0:
        for I_pop in I_pops:
            I_xIs = nest.GetStatus(I_pop, 'I_e')
            nest.SetStatus(I_pop, [{'I_e': (
                1 - 0.5 * delta_I_xI +
                np.random.rand() * delta_I_xI) * ixi} for ixi in I_xIs])
    # print nest.GetStatus(E_pops[-1],'I_e'),nest.GetStatus(I_pops[-1],'I_e'),
    # set some random initial value for the membrane voltage
    if V_m == 'rand':
        T_0_E = t_ref + FPT(tau_E, E_L, I_xE, C_m, V_th_E, V_r)
        if np.isnan(T_0_E):
            T_0_E = 10.
        for E_pop in E_pops:
            nest.SetStatus(E_pop, [{'V_m': V_FPT(
                tau_E, E_L, I_xE, C_m, T_0_E * np.random.rand(),
                V_th_E, t_ref)} for i in range(len(E_pop))])

        T_0_I = t_ref + FPT(tau_I, E_L, I_xI, C_m, V_th_I, V_r)
        if np.isnan(T_0_I):
            T_0_I = 10.
        for I_pop in I_pops:
            nest.SetStatus(I_pop, [{'V_m': V_FPT(
                tau_I, E_L, I_xI, C_m, T_0_I * np.random.rand(),
                V_th_E, t_ref)} for i in range(len(I_pop))])
    else:
        nest.SetStatus(tuple(range(1, N + 1)),
                       [{'V_m': V_m} for i in range(N)])
    # print E_pops[0]
    # nest.SetStatus([2],[{'I_e':0.}])
    # print 'E'
    # print nest.GetStatus(E_pops[0])
    # print 'I'
    # print nest.GetStatus(I_pops[0])
    # define the synapses and connect the populations
    # EE
    j_ee = js[0, 0] / np.sqrt(N)

    nest.CopyModel("static_synapse", "EE_plus", {
                   "weight": jplus[0, 0] * j_ee, "delay": delay})
    nest.CopyModel("static_synapse", "EE_minus", {
                   "weight": jminus[0, 0] * j_ee, "delay": delay})
    nest.CopyModel("static_synapse", "EE", {"weight": j_ee, "delay": delay})

    print(('jplus', jplus))
    print(('jminus', jminus))    
    for i, pre in enumerate(E_pops):
        for j, post in enumerate(E_pops):
            if fixed_indegree:
                K_EE = int(ps[0, 0] * len(pre))
                # print 'K_EE: ',K_EE
                conn_params_EE = {
                    'rule': 'fixed_indegree', 'indegree': K_EE,
                    'autapses': False, 'multapses': False}
            else:
                conn_params_EE = {'rule': 'pairwise_bernoulli',
                                  'p': ps[0, 0], 'autapses': False,
                                  'multapses': False}
            if i == j:
                # same cluster
                nest.Connect(pre, post, conn_params_EE, 'EE_plus')
            elif Q > 1 and max(i, j) == Q:
                nest.Connect(pre, post, conn_params_EE, 'EE')
            else:
                nest.Connect(pre, post, conn_params_EE, 'EE_minus')

    # EI
    j_ei = js[0, 1] / np.sqrt(N)
    nest.CopyModel("static_synapse", "EI_plus", {
                   "weight": j_ei * jplus[0, 1], "delay": delay})
    nest.CopyModel("static_synapse", "EI_minus", {
                   "weight": j_ei * jminus[0, 1], "delay": delay})
    nest.CopyModel("static_synapse", "EI", {"weight": j_ei, "delay": delay})
    pair_lst = []    
    for i, pre in enumerate(I_pops):
        for j, post in enumerate(E_pops):
            if fixed_indegree:
                K_EI = int(ps[0, 1] * len(pre))
                # print 'K_EI: ',K_EI
                conn_params_EI = {
                    'rule': 'fixed_indegree', 'indegree': K_EI,
                    'autapses': False, 'multapses': False}
            else:
                conn_params_EI = {'rule': 'pairwise_bernoulli',
                                  'p': ps[0, 1], 'autapses': False,
                                  'multapses': False}
            if i == j/portion_I:
                # same cluster
                nest.Connect(pre, post, conn_params_EI, 'EI_plus')
                pair_lst.append((i,j))
            elif Q > 1 and (i == Q/portion_I or j == Q):
                nest.Connect(pre, post, conn_params_EI, 'EI')
            else:
                nest.Connect(pre, post, conn_params_EI, 'EI_minus')
    print(("portion, i, j", portion_I, pair_lst))
    # IE
    j_ie = js[1, 0] / np.sqrt(N)
    nest.CopyModel("static_synapse", "IE_plus", {
                   "weight": j_ie * jplus[1, 0], "delay": delay})
    nest.CopyModel("static_synapse", "IE_minus", {
                   "weight": j_ie * jminus[1, 0], "delay": delay})
    nest.CopyModel("static_synapse", "IE", {"weight": j_ie, "delay": delay})
    pair_lst = []                
    for i, pre in enumerate(E_pops):
        for j, post in enumerate(I_pops):
            if fixed_indegree:
                K_IE = int(ps[1, 0] * len(pre))
                # print 'K_IE: ',K_IE
                conn_params_IE = {
                    'rule': 'fixed_indegree', 'indegree': K_IE,
                    'autapses': False, 'multapses': False}
            else:
                conn_params_IE = {'rule': 'pairwise_bernoulli',
                                  'p': ps[1, 0], 'autapses': False,
                                  'multapses': False}
            if i/portion_I == j:
                # same cluster
                nest.Connect(pre, post, conn_params_IE, 'IE_plus')
                pair_lst.append((i,j))
            elif Q > 1 and (j == Q/portion_I or i == Q):
                nest.Connect(pre, post, conn_params_IE, 'IE')
            else:
                nest.Connect(pre, post, conn_params_IE, 'IE_minus')
    print(("portion, i, j", portion_I, pair_lst))
    print(("len Ipop, portion", len(I_pops), portion_I))
    print(("jplus, jminus: ", jplus, jminus))
    # II
    j_ii = js[1, 1] / np.sqrt(N)
    nest.CopyModel("static_synapse", "II_plus", {
                   "weight": j_ii * jplus[1, 1], "delay": delay})
    nest.CopyModel("static_synapse", "II_minus", {
                   "weight": j_ii * jminus[1, 1], "delay": delay})
    nest.CopyModel("static_synapse", "II", {"weight": j_ii, "delay": delay})

    for i, pre in enumerate(I_pops):
        for j, post in enumerate(I_pops):
            if fixed_indegree:
                K_II = int(ps[1, 1] * len(pre))
                # print 'K_II: ',K_II
                conn_params_II = {
                    'rule': 'fixed_indegree', 'indegree': K_II,
                    'autapses': False, 'multapses': False}
            else:
                conn_params_II = {'rule': 'pairwise_bernoulli',
                                  'p': ps[1, 1], 'autapses': False,
                                  'multapses': False}
            if i == j:
                # same cluster
                nest.Connect(pre, post, conn_params_II, 'II_plus')
            elif Q > 1 and max(i, j) == Q:
                # one population in background
                nest.Connect(pre, post, conn_params_II, 'II')
            else:
                nest.Connect(pre, post, conn_params_II, 'II_minus')
    print(('Js: ', js / np.sqrt(N)))

    # set up spike detector
    spike_detector = nest.Create("spike_detector")
    nest.SetStatus(spike_detector, [
                   {'to_file': False, 'withtime': True, 'withgid': True}])
    all_units = ()
    for E_pop in E_pops:
        all_units += E_pop
    for I_pop in I_pops:
        all_units += I_pop
    nest.Connect(all_units, spike_detector, syn_spec='EE_plus')

    # set up stimulation
    if stim_clusters is not None:
        current_source = nest.Create('step_current_generator')
        amplitude_values = []
        amplitude_times = []
        for start, end in zip(stim_starts, stim_ends):
            amplitude_times.append(start + warmup)
            amplitude_values.append(stim_amp)
            amplitude_times.append(end + warmup)
            amplitude_values.append(0.)
        print('amplitude_times', amplitude_times)
        nest.SetStatus(current_source,
                       {'amplitude_times': amplitude_times,
                        'amplitude_values': amplitude_values,
                        'allow_offgrid_times':True})
        stim_units = []
        for stim_cluster in stim_clusters:
            stim_units += list(E_pops[stim_cluster])
        nest.Connect(current_source, stim_units)

    elif multi_stim_clusters is not None:
        for stim_clusters, amplitudes, times in zip(
                multi_stim_clusters, multi_stim_amps, multi_stim_times):
            current_source = nest.Create('step_current_generator')
            #nest.SetStatus(current_source,
            #               {'amplitude_times': np.ceil(np.array(times[1:])*10)/10,
            #                'amplitude_values': amplitudes[1:]})
            print('#####times', times[0:5], np.shape(times))
            #times = np.ceil(np.array(times)*10)/10.
            #times[0] += 0.1#sys.float_info.epsilon
            nest.SetStatus(current_source,
                           {'amplitude_times': times[1:],
                            'amplitude_values': amplitudes[1:],
                            'allow_offgrid_times':True})
            stim_units = []
            for stim_cluster in stim_clusters:
                stim_units += list(E_pops[stim_cluster])
            nest.Connect(current_source, stim_units)

    # set up multimeter if necessary
    if record_voltage:
        recordables = params.get(
            'recordables', [str(r) for r in nest.GetStatus(
                E_pops[0], 'recordables')[0]])
        voltage_recorder = nest.Create('multimeter',
                                       params={'record_from': recordables,
                                               'interval': recording_interval})
        if record_from != 'all':
            record_units = []
            for E_pop in E_pops:
                record_units += list(E_pop[:record_from])
                print((E_pop[:record_from]))
            for I_pop in I_pops:
                record_units += list(I_pop[:record_from])

        else:
            record_units = [u for u in all_units]
        nest.Connect(voltage_recorder, record_units)

    endbuild = time.time()
    print('#####', simtime, warmup)
    print(('####', warmup + simtime, int(warmup + simtime)))
    nest.Simulate(int(warmup + simtime))
    endsim = time.time()
    # get the spiketimes from the detector
    print('extracting spike times')
    events = nest.GetStatus(spike_detector, 'events')[0]
    # convert them to the format accepted by spiketools
    spiketimes = np.append(
        events['times'][None, :], events['senders'][None, :], axis=0)
    spiketimes[1] -= 1
    # remove the pre warmup spikes
    spiketimes = spiketimes[:, spiketimes[0] >= warmup]

    spiketimes[0] -= warmup

    results = {'spiketimes': spiketimes}
    if record_voltage:

        print('extracting recordables')

        events = nest.GetStatus(voltage_recorder, 'events')[0]

        times = events['times']
        senders = events['senders']
        usenders = np.unique(senders)
        sender_ind_dict = {s: record_units.index(s) for s in usenders}
        sender_inds = [sender_ind_dict[s] for s in senders]

        utimes = np.unique(times)
        time_ind_dict = {t: i for i, t in enumerate(utimes)}
        time_inds = [time_ind_dict[t] for t in times]

        if record_from == 'all':
            n_records = N
        else:
            n_records = record_from * (len(E_pops) + len(I_pops))
        print(('n_records', n_records))
        for recordable in recordables:
            t0 = time.time()

            results[recordable] = np.zeros((n_records, len(utimes)))
            results[recordable][sender_inds, time_inds] = events[recordable]
            
            results[recordable] = results[recordable][:, utimes >= warmup]

        utimes = utimes[utimes >= warmup]
        utimes -= warmup
        results['senders'] = np.array(record_units)
        results['times'] = utimes

    if return_weights:
        print('extracting weight matrix')

        connections = [c for c in nest.GetConnections() if c[0]
                       <= N and c[1] <= N]
        pre = [c[0] - 1 for c in connections]
        post = [c[1] - 1 for c in connections]
        synapse_ids = [c[3] for c in connections]
        unique_synapse_ids, inds = np.unique(synapse_ids, return_index=True)
        unique_synaptic_weights = nest.GetStatus(
            [connections[i] for i in inds], keys='weight')
        weights = np.zeros((len(synapse_ids)))
        for i, uid in enumerate(unique_synapse_ids):
            weights[synapse_ids == uid] = unique_synaptic_weights[i]
        weight_mat = np.zeros((N, N))
        weight_mat[post, pre] = weights
        results['weights'] = csr_matrix(weight_mat)

    e_count = spiketimes[:, spiketimes[1] < N_E].shape[1]
    i_count = spiketimes[:, spiketimes[1] >= N_E].shape[1]
    e_rate = e_count / float(N_E) / float(simtime) * 1000.
    i_rate = i_count / float(N_I) / float(simtime) * 1000.

    results['e_rate'] = e_rate
    results['i_rate'] = i_rate
    results['I_xE'] = I_xE
    results['I_xI'] = I_xI
    endpost = time.time()

    print('Done')
    print(('build time: ', endbuild - startbuild))
    print(('simulation time: ', endsim - endbuild))
    print(('post processing time: ', endpost - endsim))

    return results


def tune_rates_grid_search(
        params, target_rates=[3., 5.],
        warmup=1000, simtime=5000, npoints=10,
        jxs_ranges=[[0, 0.1], [0, 0.1]], maxrounds=20, reps=5):
    original_params = deepcopy(params)
    params['warmup'] = warmup
    params['simtime'] = simtime

    def optfunce(jex):
        params['jex'] = jex[0]

        e_rates = []
        i_rates = []
        for r in range(reps):
            result = simulate(params)
            e_rates.append(result['e_rate'])
            i_rates.append(result['i_rate'])
        e_rate = np.array(e_rates).mean()
        i_rate = np.array(i_rates).mean()
        print(('rates: ', e_rate, i_rate))
        offset = 0
        if e_rate < 0.1 or i_rate < 0.1:
            offset = 10000
        return (e_rate - target_rates[0])**2 +\
            (i_rate - target_rates[1])**2 + offset

    def optfunci(jix):
        params['jix'] = jix[0]

        e_rates = []
        i_rates = []
        for r in range(reps):
            result = simulate(params)
            e_rates.append(result['e_rate'])
            i_rates.append(result['i_rate'])
        e_rate = np.array(e_rates).mean()
        i_rate = np.array(i_rates).mean()
        print(('rates: ', e_rate, i_rate))
        offset = 0
        if e_rate < 0.1 or i_rate < 0.1:
            offset = 100000.
        return (e_rate - target_rates[0])**2 +\
            (i_rate - target_rates[1])**2 + offset

    jexgrid = np.unique(np.linspace(
        jxs_ranges[0][0], jxs_ranges[0][1], npoints))

    jixgrid = np.unique(np.linspace(
        jxs_ranges[1][0], jxs_ranges[1][1], npoints))

    print((jexgrid, jixgrid))
    params['jex'] = jexgrid[len(jexgrid) / 2]
    params['jix'] = jixgrid[len(jixgrid) / 2]
    for round in range(maxrounds):

        oldjex = params['jex']
        oldjix = params['jix']
        vals = pylab.zeros_like(jexgrid)
        for i, jex in enumerate(jexgrid):

            vals[i] = optfunce([jex])
        best = np.argmin(vals)
        params['jex'] = jexgrid[best]
        print(vals)
        vals = pylab.zeros_like(jixgrid)
        for i, jix in enumerate(jixgrid):

            vals[i] = optfunci([jix])
        best = np.argmin(vals)
        params['jix'] = jixgrid[best]

        print((oldjex, params['jex'], oldjix, params['jix']))
        if oldjex == params['jex'] and oldjix == params['jix']:
            break

    jxs = [params['jex'], params['jix']]
    params = original_params
    return jxs


def tune_rates(
        params, target_rates=[15., 10.],
        warmup=1000, simtime=5000, start_I_ths=[1., 1.],
        max_eval=1000, reps=5, separate=True, runs=50,
        ftol=0.1, xtol=0.001):
    original_params = deepcopy(params)
    params['warmup'] = warmup
    params['simtime'] = simtime

    if separate:
        params['I_th_E'] = start_I_ths[0]
        params['I_th_I'] = start_I_ths[1]

        def optfunce(ithe):
            params['I_th_E'] = ithe[0]
            params['I_th_I'] = iths[1]
            if ithe[0] <= 0:
                return 10000.
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()

            print(('rates: ', e_rate, i_rate))
            if pylab.absolute(
                    e_rate - target_rates[0]) < ftol and pylab.absolute(
                        i_rate - target_rates[1]) < ftol:
                error = 0
            else:
                error = (e_rate - target_rates[0])**2 + \
                    (i_rate - target_rates[1])**2
            print(error)
            return error

        def optfunci(ithi):
            params['I_th_I'] = ithi[0]
            params['I_th_E'] = iths[0]
            if ithi[0] <= 0:
                return 10000.
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()
            print(('rates: ', e_rate, i_rate))
            if pylab.absolute(
                    e_rate - target_rates[0]) < ftol and pylab.absolute(
                        i_rate - target_rates[1]) < ftol:
                error = 0
            else:
                error = (e_rate - target_rates[0])**2 + \
                    (i_rate - target_rates[1])**2
            print(error)
            return error
        iths = start_I_ths
        for run in range(runs):
            print(iths)
            iths[0] = fmin(optfunce, [iths[0]], ftol=ftol,
                           maxfun=max_eval / (2 * runs), xtol=xtol)[0]
            print(iths)
            iths[1] = fmin(optfunci, [iths[1]], ftol=ftol,
                           maxfun=max_eval / (2 * runs), xtol=xtol)[0]

    else:
        def optfunc(iths):
            print(iths)
            if min(iths) < 0:
                return 1000.
            params['I_th_E'] = iths[0]
            params['I_th_I'] = iths[1]
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()
            print(('rates: ', e_rate, i_rate))
            if pylab.absolute(
                    e_rate - target_rates[0]) < ftol and pylab.absolute(
                        i_rate - target_rates[1]) < ftol:
                error = 0
            else:
                error = (e_rate - target_rates[0])**2 + \
                    (i_rate - target_rates[1])**2
            print(error)
            return error

        iths = fmin(optfunc, start_I_ths,
                    maxfun=max_eval, ftol=ftol, xtol=xtol)
    params = original_params
    return iths


def tune_rate_threshold(
        params, target_rates=[3., 5.], warmup=1000,
        simtime=5000, start_V_ths=[1., 1.], max_eval=1000,
        reps=5, separate=True, runs=50, ftol=0.1):
    original_params = deepcopy(params)
    params['warmup'] = warmup
    params['simtime'] = simtime

    if separate:
        params['V_th_E'] = start_V_ths[0]
        params['V_th_I'] = start_V_ths[1]

        def optfunce(V_ths):

            params['V_th_E'] = V_ths[0]

            print(('e, ', params['V_th_E'], params['V_th_I']))

            if V_ths[0] <= 0:
                return 100000.
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()
            print(('rates: ', e_rate, i_rate))
            offset = 0
            if e_rate < 0.1 or i_rate < 0.1:
                offset = 10000
            return offset + (
                e_rate - target_rates[0])**2 + (i_rate - target_rates[1])**2

        def optfunci(V_ths):

            params['V_th_I'] = V_ths[0]
            print(('i, ', params['V_th_E'], params['V_th_I']))
            if V_ths[0] <= 0:
                return 100000.
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()
            print(('rates: ', e_rate, i_rate))
            offset = 0
            if e_rate < 0.1 or i_rate < 0.1:
                offset = 10000
            return offset + (
                e_rate - target_rates[0])**2 + (i_rate - target_rates[1])**2
        V_ths = start_V_ths
        for run in range(runs):
            print(('run: ', run, max_eval / (2 * runs)))
            V_ths[0] = fmin(optfunce, [V_ths[0]], ftol=ftol, maxfun=max_eval /
                            (2 * runs), maxiter=max_eval / (2 * runs), disp=True)
            V_ths[1] = fmin(optfunci, [V_ths[1]], ftol=ftol, maxfun=max_eval /
                            (2 * runs), maxiter=max_eval / (2 * runs), disp=True)

    else:
        def optfunc(V_ths):
            print((params['V_th_E'], params['V_th_I']))
            params['V_th_E'] = V_ths[0]
            params['V_th_I'] = V_ths[1]
            e_rates = []
            i_rates = []
            for r in range(reps):
                result = simulate(params)
                e_rates.append(result['e_rate'])
                i_rates.append(result['i_rate'])
            e_rate = np.array(e_rates).mean()
            i_rate = np.array(i_rates).mean()
            print(('rates: ', e_rate, i_rate))
            offset = 0
            if e_rate < 0.1 or i_rate < 0.1:
                offset = 10000

            return offset + (
                e_rate - target_rates[0])**2 + (i_rate - target_rates[1])**2

        V_ths = fmin(optfunc, start_V_ths, maxfun=max_eval, ftol=ftol)
    params = original_params
    return V_ths


if __name__ == '__main__':
    #import plotting
    js_maz = pylab.array([[1.77, -3.18], [1.06, -4.24]])

    params = {'warmup':0,'simtime':2000.,'n_jobs':12,'Q':50,'rate_kernel':50,
              'record_voltage': True,
              'record_from': 1,
              'randseed':1, 'jep':8.}

    jip_ratio = 0.75
    jep = 8. # 3.7 # 7.5 # 
    jip = 1. + (jep - 1) * jip_ratio
    params['jplus'] = pylab.array([[jep, jip], [jip, jip]])
    
    js = calc_js(params)
    print(('us: ', js / js[0, 0]))
    print(('mazzucato: ', js_maz / js_maz[0, 0]))
    #N = params['N_E'] + params['N_I']
    params['portion_I'] = 1 # 
    # params['ps'] = pylab.ones((2,2))*0.2
    #I_ths = tune_rates(params,start_I_ths = [1.,0.1],
    #warmup =200,simtime = 500,separate = False,
    #reps =1,ftol = 0.05,xtol = 0.01,runs = 10,max_eval  =1000)
    I_ths = [2.13, 1.24]  # 3,5,Hz
    #I_ths = [5.34, 2.61]  # 10,15,Hz
    # params['mazzicato_js'] = True
    # I_ths = [1.01,0.98]
    #print 'result: ', I_ths
    params['I_th_E'] = I_ths[0]
    params['I_th_I'] = I_ths[1]

    params['Q'] = 50
    params['fixed_indegree'] = True
    jip_ratio = 0.75
    jep = 8. # 3.7 # 7.5 # 
    jip = 1. + (jep - 1) * jip_ratio
    params['jplus'] = pylab.array([[jep, jip], [jip, jip]])
    # params['neuron_type'] = 'iaf_psc_delta'

    results = simulate(params)

    spiketimes = results['spiketimes']
    pylab.subplot(2, 1, 1)
    pylab.plot(spiketimes[0], spiketimes[1], '.k', markersize=1)
    pylab.title(str(results['e_rate']) + ', ' + str(results['i_rate']))
    # pylab.subplot(2, 1, 2)
    # plotting.psth_plot(
    #     spiketimes[:, spiketimes[1] < params['N_E']], binsize=5.)

    # pylab.figure()
    # E_inds = pylab.find(results['senders'] < params['N_E'])
    # I_inds = pylab.find(results['senders'] >= params['N_E'])
    # pylab.subplot(2, 1, 1)
    # pylab.plot(results['times'], results['V_m'][E_inds].T)
    # pylab.subplot(2, 1, 2)
    # pylab.plot(results['times'], results['V_m'][I_inds].T)

    pylab.show()
