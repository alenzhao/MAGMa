package org.nlesc.magma.resources;

import javax.ws.rs.POST;
import javax.ws.rs.Path;

import org.nlesc.magma.BrokerFactory;
import org.nlesc.magma.JobDescriptionFactory;
import org.nlesc.magma.JobStateListener;
import org.nlesc.magma.entities.JobSubmitRequest;
import org.nlesc.magma.entities.JobSubmitResponse;

import org.gridlab.gat.GAT;
import org.gridlab.gat.resources.Job;
import org.gridlab.gat.resources.JobDescription;
import org.gridlab.gat.resources.ResourceBroker;

@Path("/job")
public class JobResource {
    protected JobDescriptionFactory jobdescriptionfactory;
    protected BrokerFactory brokerfactory;

    public JobResource() {
        super();
        this.jobdescriptionfactory = new JobDescriptionFactory();
        this.brokerfactory = new BrokerFactory();
    }

    public void setBroker(BrokerFactory broker) {
        this.brokerfactory = broker;
    }

    @POST
    public JobSubmitResponse submitJob(JobSubmitRequest jobsubmission)
            throws Exception {

        JobDescription jd = this.jobdescriptionfactory
                .getJobDescription(jobsubmission);
        ResourceBroker broker = this.brokerfactory.getBroker();

        JobStateListener cb = new JobStateListener(
                GAT.createFile(jobsubmission.jobdir));
        Job job = broker.submitJob(jd, cb, "job.status");

        // TODO Store somevar[jobid] = state,
        // update it in callback so GET /job/{jobid} returns state
        return new JobSubmitResponse(Integer.toString(job.getJobID()));
    }
}
