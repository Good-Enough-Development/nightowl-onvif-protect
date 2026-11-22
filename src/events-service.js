'use strict';

const fs = require('fs');
const { randomUUID } = require('crypto');
const { parseStringPromise, processors } = require('xml2js');

const TOPIC = 'tns1:RuleEngine/CellMotionDetector/Motion';
const NS = `xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:wsa="http://www.w3.org/2005/08/addressing" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
 xmlns:wstop="http://docs.oasis-open.org/wsn/t-1" xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
 xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tns1="http://www.onvif.org/ver10/topics"
 xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:ter="http://www.onvif.org/ver10/error"`;
const escapeXml = value => String(value).replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const iso = ms => new Date(ms).toISOString();
const text = value => value && typeof value === 'object' ? value._ : value;
function duration(value, fallback) {
    value = text(value);
    const m = typeof value === 'string' && /^PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$/.exec(value);
    if (m) return (+m[1]||0)*3600000+(+m[2]||0)*60000+(+m[3]||0)*1000;
    if (value && Number.isFinite(Date.parse(value))) return Math.max(0,Date.parse(value)-Date.now());
    return fallback;
}

class EventsService {
    constructor(config, logger) {
        this.config=config;
        this.logger=logger;
        this.subscriptions=new Map();
        this.active=false;
        this.motionAt=Date.now();
        this.stats={subscriptionsCreated:0,pulls:0,notificationsDelivered:0,transitions:0};
        this.timer=setInterval(()=>this.refresh(),250);
        this.timer.unref();
        this.refresh();
    }
    address() { return `http://${this.config.hostname}:${this.config.ports.server}/onvif/events_service`; }
    log(message) { this.logger.info(`[EVENTS ${this.config.name}] ${message}`); }
    refresh() {
        let active=false, when=Date.now();
        try {
            const record=JSON.parse(fs.readFileSync(this.config.motion.stateFile,'utf8'));
            const age=Date.now()-Date.parse(record.updatedAt);
            if (record.channel===this.config.motion.channel && age>=-5000 && age<15000) {
                active=record.active===true && record.status==='running';
                const t=Date.parse(record.transitionAt);
                if (Number.isFinite(t) && Math.abs(Date.now()-t)<3600000) when=t;
            }
        } catch (_) { /* Missing or stale producer always clears motion. */ }
        this.setMotion(active,when);
        const now=Date.now();
        for (const [id,sub] of this.subscriptions) {
            if (sub.termination<now && !sub.pending) this.subscriptions.delete(id);
        }
    }
    setMotion(active, when=Date.now()) {
        if (active===this.active) return;
        this.active=active;
        this.motionAt=when;
        this.stats.transitions++;
        const message=this.notification(active,when,'Changed');
        for (const sub of this.subscriptions.values()) {
            sub.queue.push(message);
            if (sub.queue.length>128) sub.queue.shift();
            if (sub.pending) sub.pending();
        }
        this.log(`motion=${active} subscribers=${this.subscriptions.size}`);
    }
    notification(active,when,operation) {
        return `<wsnt:NotificationMessage><wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">${TOPIC}</wsnt:Topic>
<wsnt:Message><tt:Message UtcTime="${iso(when)}" PropertyOperation="${operation}">
<tt:Source><tt:SimpleItem Name="VideoSourceConfigurationToken" Value="video_src_config_token"/><tt:SimpleItem Name="RuleName" Value="MotionDetector"/></tt:Source>
<tt:Data><tt:SimpleItem Name="IsMotion" Value="${active?'true':'false'}"/></tt:Data>
</tt:Message></wsnt:Message></wsnt:NotificationMessage>`;
    }
    envelope(body,action,relatesTo) {
        return `<?xml version="1.0" encoding="UTF-8"?><s:Envelope ${NS}><s:Header>
<wsa:Action s:mustUnderstand="true">${escapeXml(action)}</wsa:Action><wsa:MessageID>urn:uuid:${randomUUID()}</wsa:MessageID>
${relatesTo?`<wsa:RelatesTo>${escapeXml(relatesTo)}</wsa:RelatesTo>`:''}</s:Header><s:Body>${body}</s:Body></s:Envelope>`;
    }
    send(response,body,action,relatesTo,status=200) {
        if (response.destroyed || response.writableEnded) return;
        response.writeHead(status,{'Content-Type':`application/soap+xml; charset=utf-8; action="${action}"`,'Cache-Control':'no-store'});
        response.end(this.envelope(body,action,relatesTo));
    }
    fault(response,message,relatesTo,subcode='ter:InvalidArgVal') {
        this.send(response,`<s:Fault><s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>${subcode}</s:Value></s:Subcode></s:Code><s:Reason><s:Text xml:lang="en">${escapeXml(message)}</s:Text></s:Reason></s:Fault>`,
            'http://www.w3.org/2005/08/addressing/fault',relatesTo,500);
    }
    properties() {
        return `<tev:GetEventPropertiesResponse>
<tev:TopicNamespaceLocation>http://www.onvif.org/ver10/topics/topicns.xml</tev:TopicNamespaceLocation><tev:FixedTopicSet>true</tev:FixedTopicSet>
<wstop:TopicSet><tns1:RuleEngine><CellMotionDetector><Motion wstop:topic="true">
<tt:MessageDescription IsProperty="true"><tt:Source><tt:SimpleItemDescription Name="VideoSourceConfigurationToken" Type="tt:ReferenceToken"/><tt:SimpleItemDescription Name="RuleName" Type="xs:string"/></tt:Source>
<tt:Data><tt:SimpleItemDescription Name="IsMotion" Type="xs:boolean"/></tt:Data></tt:MessageDescription>
</Motion></CellMotionDetector></tns1:RuleEngine></wstop:TopicSet>
<tev:TopicExpressionDialect>http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet</tev:TopicExpressionDialect>
<tev:TopicExpressionDialect>http://docs.oasis-open.org/wsn/t-1/TopicExpression/Simple</tev:TopicExpressionDialect>
<tev:MessageContentFilterDialect>http://www.onvif.org/ver10/tev/messageContentFilter/ItemFilter</tev:MessageContentFilterDialect>
<tev:MessageContentSchemaLocation>http://www.onvif.org/ver10/schema/onvif.xsd</tev:MessageContentSchemaLocation></tev:GetEventPropertiesResponse>`;
    }
    handle(request,response) {
        const parsed=new URL(request.url,'http://localhost');
        if (parsed.pathname==='/motion/status' && request.method==='GET') {
            response.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});
            response.end(JSON.stringify({camera:this.config.name,channel:this.config.motion.channel,active:this.active,subscribers:this.subscriptions.size,...this.stats}));
            return true;
        }
        if (parsed.pathname!=='/onvif/events_service' && !parsed.pathname.startsWith('/onvif/events_service/')) return false;
        if (request.method!=='POST') { response.writeHead(405,{'Allow':'POST'}); response.end(); return true; }
        let body='',tooLarge=false;
        request.on('data',chunk=>{
            body+=chunk;
            if (body.length>65536 && !tooLarge) {tooLarge=true;response.writeHead(413);response.end();}
        });
        request.on('end',async()=>{
            if (tooLarge) return;
            try {
                if (/<!DOCTYPE|<!ENTITY/i.test(body)) throw new Error('DTD is not supported');
                const xml=await parseStringPromise(body,{explicitArray:false,tagNameProcessors:[processors.stripPrefix]});
                const envelope=xml.Envelope;
                const entry=Object.entries(envelope.Body).find(([key])=>key!=='$');
                if (!entry) throw new Error('Missing SOAP operation');
                const [operation,argsValue]=entry;
                const args=argsValue||{};
                const relatesTo=text(envelope.Header?.MessageID);
                this.dispatch(operation,args,parsed.searchParams.get('sub'),response,relatesTo);
            } catch (e) { this.fault(response,'Invalid SOAP event request'); }
        });
        return true;
    }
    dispatch(operation,args,id,response,relatesTo) {
        const prefix='http://www.onvif.org/ver10/events/wsdl/';
        if (operation==='GetEventProperties') {
            this.log('GetEventProperties');
            return this.send(response,this.properties(),prefix+'EventPortType/GetEventPropertiesResponse',relatesTo);
        }
        if (operation==='GetServiceCapabilities') return this.send(response,
            '<tev:GetServiceCapabilitiesResponse><tev:Capabilities WSSubscriptionPolicySupport="false" WSPullPointSupport="true" WSPausableSubscriptionManagerInterfaceSupport="false" MaxNotificationProducers="16" MaxPullPoints="16" PersistentNotificationStorage="false"/></tev:GetServiceCapabilitiesResponse>',
            prefix+'EventPortType/GetServiceCapabilitiesResponse',relatesTo);
        if (operation==='CreatePullPointSubscription') {
            this.refresh();
            if (this.subscriptions.size>=16) return this.fault(response,'Too many subscriptions',relatesTo);
            id=randomUUID();
            const now=Date.now();
            const lifetime=Math.min(3600000,Math.max(60000,duration(args.InitialTerminationTime,300000)));
            const sub={termination:now+lifetime,queue:[this.notification(this.active,now,'Initialized')],pending:null};
            this.subscriptions.set(id,sub);
            this.stats.subscriptionsCreated++;
            this.log(`CreatePullPointSubscription client subscription=${id}`);
            return this.send(response,`<tev:CreatePullPointSubscriptionResponse><tev:SubscriptionReference><wsa:Address>${escapeXml(this.address()+'?sub='+id)}</wsa:Address></tev:SubscriptionReference><wsnt:CurrentTime>${iso(now)}</wsnt:CurrentTime><wsnt:TerminationTime>${iso(sub.termination)}</wsnt:TerminationTime></tev:CreatePullPointSubscriptionResponse>`,
                prefix+'EventPortType/CreatePullPointSubscriptionResponse',relatesTo);
        }
        const sub=this.subscriptions.get(id);
        if (!sub || sub.termination<Date.now()) return this.fault(response,'Subscription does not exist or has expired',relatesTo,'wsnt:ResourceUnknownFault');
        if (operation==='PullMessages') {
            if (sub.pending) return this.fault(response,'A pull is already pending for this subscription',relatesTo);
            const timeout=Math.min(60000,Math.max(0,duration(args.Timeout,60000)));
            const limit=Math.min(128,Math.max(1,parseInt(text(args.MessageLimit)||'10',10)||10));
            sub.termination=Math.max(sub.termination,Date.now()+timeout+60000);
            this.stats.pulls++;
            let timer;
            const finish=()=>{
                clearTimeout(timer);sub.pending=null;
                const messages=sub.queue.splice(0,limit);
                this.stats.notificationsDelivered+=messages.length;
                if (messages.length) this.log(`PullMessages delivered=${messages.length} subscription=${id}`);
                this.send(response,`<tev:PullMessagesResponse><tev:CurrentTime>${iso(Date.now())}</tev:CurrentTime><tev:TerminationTime>${iso(sub.termination)}</tev:TerminationTime>${messages.join('')}</tev:PullMessagesResponse>`,prefix+'PullPointSubscription/PullMessagesResponse',relatesTo);
            };
            if (sub.queue.length || timeout===0) return finish();
            sub.pending=finish;
            timer=setTimeout(finish,timeout);
            response.once('close',()=>{ if (sub.pending===finish) {clearTimeout(timer);sub.pending=null;} });
            return;
        }
        if (operation==='Renew') {
            sub.termination=Date.now()+Math.min(3600000,Math.max(60000,duration(args.TerminationTime,300000)));
            return this.send(response,`<wsnt:RenewResponse><wsnt:TerminationTime>${iso(sub.termination)}</wsnt:TerminationTime><wsnt:CurrentTime>${iso(Date.now())}</wsnt:CurrentTime></wsnt:RenewResponse>`,
                'http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/RenewResponse',relatesTo);
        }
        if (operation==='SetSynchronizationPoint') {
            sub.queue.push(this.notification(this.active,Date.now(),'Initialized'));
            if (sub.pending) sub.pending();
            return this.send(response,'<tev:SetSynchronizationPointResponse/>',prefix+'PullPointSubscription/SetSynchronizationPointResponse',relatesTo);
        }
        if (operation==='Unsubscribe') {
            if (sub.pending) sub.pending();
            this.subscriptions.delete(id);
            return this.send(response,'<wsnt:UnsubscribeResponse/>','http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeResponse',relatesTo);
        }
        return this.fault(response,'Unsupported event operation',relatesTo,'ter:ActionNotSupported');
    }
    close() { clearInterval(this.timer); for (const sub of this.subscriptions.values()) if(sub.pending)sub.pending(); this.subscriptions.clear(); }
}
module.exports={EventsService,TOPIC};
