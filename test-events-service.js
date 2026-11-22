'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {EventsService}=require('./src/events-service');

test('PullPoint delivers motion edges per camera, waits correctly, and clears stale producers',async()=>{
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'nightowl-events-test-'));
    const services=[1,2].map(channel=>new EventsService({name:`test${channel}`,hostname:'127.0.0.1',ports:{server:0},motion:{channel,stateFile:path.join(dir,`${channel}.json`)}},{info(){}}));
    const server=http.createServer((req,res)=>{
        const camera=+req.headers['x-test-camera']||1;
        if (!services[camera-1].handle(req,res)) {res.writeHead(404);res.end();}
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const port=server.address().port;
    services.forEach(s=>s.config.ports.server=port);
    async function soap(camera,operation,body='',sub='') {
        const response=await fetch(`http://127.0.0.1:${port}/onvif/events_service${sub?'?sub='+sub:''}`,{
            method:'POST',headers:{'Content-Type':'application/soap+xml','x-test-camera':String(camera)},
            body:`<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tev="http://www.onvif.org/ver10/events/wsdl"><s:Header/><s:Body><tev:${operation}>${body}</tev:${operation}></s:Body></s:Envelope>`});
        return {status:response.status,xml:await response.text()};
    }
    try {
        const properties=await soap(1,'GetEventProperties');
        assert.match(properties.xml,/<tev:FixedTopicSet>true/);
        assert.match(properties.xml,/Name="IsMotion"/);
        const ids=[];
        for (const camera of [1,2]) {
            const result=await soap(camera,'CreatePullPointSubscription','<tev:InitialTerminationTime>PT5M</tev:InitialTerminationTime>');
            const id=/\?sub=([^<]+)/.exec(result.xml)[1];ids.push(id);
            const initial=await soap(camera,'PullMessages','<tev:Timeout>PT0S</tev:Timeout><tev:MessageLimit>10</tev:MessageLimit>',id);
            assert.match(initial.xml,/PropertyOperation="Initialized"/);
            assert.match(initial.xml,/Name="IsMotion" Value="false"/);
        }
        services[0].setMotion(true);
        const a=await soap(1,'PullMessages','<tev:Timeout>PT0S</tev:Timeout><tev:MessageLimit>10</tev:MessageLimit>',ids[0]);
        assert.match(a.xml,/Name="IsMotion" Value="true"/);
        const b=await soap(2,'PullMessages','<tev:Timeout>PT0S</tev:Timeout>',ids[1]);
        assert.doesNotMatch(b.xml,/<wsnt:NotificationMessage>/);
        services[0].setMotion(true); // Duplicate level must not generate a new event.
        assert.equal(services[0].subscriptions.get(ids[0]).queue.length,0);
        const start=Date.now();
        const wait=soap(2,'PullMessages','<tev:Timeout>PT2S</tev:Timeout><tev:MessageLimit>1</tev:MessageLimit>',ids[1]);
        setTimeout(()=>services[1].setMotion(true),70);
        const awakened=await wait;
        assert.match(awakened.xml,/Name="IsMotion" Value="true"/);
        assert.ok(Date.now()-start>=50 && Date.now()-start<1500);
        services[0].refresh(); // Missing producer is fail-closed.
        const cleared=await soap(1,'PullMessages','<tev:Timeout>PT0S</tev:Timeout>',ids[0]);
        assert.match(cleared.xml,/Name="IsMotion" Value="false"/);
        const wrongCamera=await soap(2,'PullMessages','',ids[0]);
        assert.equal(wrongCamera.status,500);
        const renewed=await soap(1,'Renew','<tev:TerminationTime>PT10M</tev:TerminationTime>',ids[0]);
        assert.match(renewed.xml,/RenewResponse/);
        await soap(1,'Unsubscribe','',ids[0]);
        assert.equal((await soap(1,'PullMessages','',ids[0])).status,500);
        assert.equal((await fetch(`http://127.0.0.1:${port}/trigger/motion?state=on`)).status,404);
    } finally {
        services.forEach(s=>s.close());
        server.closeAllConnections();
        await new Promise(resolve=>server.close(resolve));
        fs.rmSync(dir,{recursive:true,force:true});
    }
});
