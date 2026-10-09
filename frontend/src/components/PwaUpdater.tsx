import { useState } from 'react'
import { registerSW } from 'virtual:pwa-register'

export default function PwaUpdater() {
  const [needRefresh,setNeedRefresh]=useState(false)
  const [offlineReady,setOfflineReady]=useState(false)
  const [updateSW]=useState(()=>registerSW({
    immediate:true,
    onNeedRefresh:()=>setNeedRefresh(true),
    onOfflineReady:()=>{setOfflineReady(true);setTimeout(()=>setOfflineReady(false),3500)},
    onRegisteredSW(_url:string,registration:ServiceWorkerRegistration|undefined){if(registration)setInterval(()=>registration.update(),60_000)},
  }))
  if(!needRefresh&&!offlineReady)return null
  return <div className="fixed bottom-20 lg:bottom-5 right-4 z-[100] max-w-sm rounded-2xl bg-gray-900 text-white shadow-2xl p-4">
    <p className="text-sm font-semibold">{needRefresh?'Dostępna jest nowa wersja FreshStock.':'Aplikacja jest gotowa do pracy offline.'}</p>
    {needRefresh&&<div className="flex gap-2 mt-3"><button onClick={()=>updateSW(true)} className="bg-green-500 px-4 py-2 rounded-xl text-sm font-bold">Aktualizuj teraz</button><button onClick={()=>setNeedRefresh(false)} className="px-3 py-2 text-sm text-gray-300">Później</button></div>}
  </div>
}
