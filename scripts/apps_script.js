// ====================================================
// SETUP INSTRUCTIONS
// 1. Paste this into Google Apps Script (Extensions >
//    Apps Script in your Google Sheet)
// 2. Click Project Settings (gear icon) > Script
//    Properties and add:
//    BACKEND_URL              = https://your-api.azurecontainer.io
//    FRONTEND_URL             = https://your-app.vercel.app
//    PARTICIPANT_REGISTER_KEY = your-secret-key
//    MONITORING_API_KEY       = your-monitoring-key
//    PAYPAL_CLIENT_ID         = your-paypal-client-id
//    PAYPAL_CLIENT_SECRET     = your-paypal-client-secret
// 3. Click Run > Run function > authoriseScript once
//    to grant Gmail and Sheets permissions
// 4. Add trigger for form submissions:
//    Triggers > Add Trigger > onFormSubmit >
//    From spreadsheet > On form submit
// 5. Add trigger for payments (hourly check):
//    Triggers > Add Trigger > checkAndPay >
//    Time-driven > Hour timer > Every hour
//
// PAYPAL SETUP
// a. Go to developer.paypal.com > Apps & Credentials
// b. Create a Live app with Payouts enabled
// c. Copy the Client ID and Secret into Script Properties
// d. Make sure your PayPal Business account has enough
//    balance (56 x £5 = £280) and Payouts is enabled
// ====================================================

const RESEARCHER_EMAIL = "ob509@exeter.ac.uk"
const YOUR_NAME = "Oluwaseyi Bello"

function authoriseScript() {
  Logger.log("Authorisation granted")
}

function getNextParticipantId(sheet) {
  const data = sheet.getDataRange().getValues()
  const headers = data[0]
  const pidCol = headers.indexOf("Participant_id")

  let maxId = 0
  for (let i = 1; i < data.length; i++) {
    const pid = data[i][pidCol]
    if (pid && pid.toString().startsWith("P")) {
      const num = parseInt(pid.toString().replace("P", ""))
      if (num > maxId) maxId = num
    }
  }

  const nextNum = maxId + 1
  const paddedNum = String(nextNum).padStart(2, "0")
  return "P" + paddedNum
}

function getCondition(pid) {
  const num = parseInt(pid.replace("P", ""))
  return num % 2 === 1 ? "baseline" : "multiagent"
}

function isEligible(row, headers) {
  const courseCol = headers.indexOf(
    "Are you currently enrolled at the University of Exeter studying Computer Science or a closely related subject?  "
  )
  const ageCol = headers.indexOf(
    "  Are you aged 18 or over?  "
  )
  const pythonCol = headers.indexOf(
    "  Are you able to write basic Python code?  "
  )

  if (courseCol === -1 || ageCol === -1 || pythonCol === -1) {
    Logger.log("ERROR: Column not found. Check header strings match exactly.")
    return false
  }

  return row[courseCol] === "Yes" &&
         row[ageCol] === "Yes" &&
         row[pythonCol] !== "No"
}

function registerWithBackend(pid, condition) {
  const props = PropertiesService.getScriptProperties()
  const backendUrl = props.getProperty("BACKEND_URL")
  const secret = props.getProperty("PARTICIPANT_REGISTER_KEY")

  if (!backendUrl || !secret) {
    Logger.log("ERROR: BACKEND_URL or PARTICIPANT_REGISTER_KEY not set in Script Properties")
    return false
  }

  try {
    const response = UrlFetchApp.fetch(
      `${backendUrl}/participants/register`,
      {
        method: "POST",
        contentType: "application/json",
        payload: JSON.stringify({
          participant_id: pid,
          condition: condition,
          secret: secret
        }),
        muteHttpExceptions: true
      }
    )

    const code = response.getResponseCode()
    if (code === 200) {
      Logger.log(`Registered ${pid} (${condition}) successfully`)
      return true
    } else {
      Logger.log(`Registration failed for ${pid}: HTTP ${code} -- ${response.getContentText()}`)
      return false
    }
  } catch (err) {
    Logger.log(`Registration error for ${pid}: ${err}`)
    return false
  }
}

function onFormSubmit(e) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet()
  const data = sheet.getDataRange().getValues()
  const headers = data[0]
  const lastRow = sheet.getLastRow()
  const row = data[lastRow - 1]

  const emailCol    = headers.indexOf("What is your University of Exeter email address?  ")
  const nameCol     = headers.indexOf("What is your full name? ")
  const pidCol      = headers.indexOf("Participant_id")
  const conditionCol = headers.indexOf("condition")
  const linkSentCol = headers.indexOf("link_sent")
  const dateSentCol = headers.indexOf("date_sent")

  if (emailCol === -1 || nameCol === -1) {
    Logger.log("ERROR: Email or name column not found. Check header strings.")
    return
  }

  if (pidCol === -1 || conditionCol === -1 || linkSentCol === -1 || dateSentCol === -1) {
    Logger.log("ERROR: Sheet column not found (Participant_id / condition / link_sent / date_sent). Check header names.")
    return
  }

  const email = row[emailCol]
  const name = row[nameCol] || "Participant"
  const firstName = name.split(" ")[0]

  if (!isEligible(row, headers)) {
    GmailApp.sendEmail(
      email,
      "RE: AI Coding Study -- Expression of Interest",
      "",
      {
        name: YOUR_NAME,
        htmlBody: `
          <p>Hi ${firstName},</p>
          <p>Thank you for your interest in my MSc research
          study on AI coding tools.</p>
          <p>Unfortunately, based on your responses you do
          not meet the eligibility criteria for this study
          at this time.</p>
          <p>Best regards,<br>${YOUR_NAME}<br>
          MSc Computer Science, University of Exeter<br>
          ${RESEARCHER_EMAIL}</p>
        `
      }
    )
    Logger.log(`Ineligible participant: ${email}`)
    return
  }

  const pid = getNextParticipantId(sheet)
  const condition = getCondition(pid)
  const registered = registerWithBackend(pid, condition)

  const props = PropertiesService.getScriptProperties()
  const frontendUrl = props.getProperty("FRONTEND_URL")
  if (!frontendUrl) {
    Logger.log("ERROR: FRONTEND_URL not set in Script Properties")
    return
  }
  const studyLink = `${frontendUrl.replace(/\/$/, "")}/study?pid=${pid}&condition=${condition}`

  if (!registered) {
    GmailApp.sendEmail(
      email,
      "AI Coding Study -- Action Required",
      "",
      {
        name: YOUR_NAME,
        htmlBody: `
          <p>Hi ${firstName},</p>
          <p>Thank you for signing up for my MSc research
          study. There was a brief technical issue processing
          your registration.</p>
          <p>Please contact me directly at
          <a href="mailto:${RESEARCHER_EMAIL}">${RESEARCHER_EMAIL}</a>
          and I will send you your study link manually.</p>
          <p>Sorry for the inconvenience.</p>
          <p>Best regards,<br>${YOUR_NAME}<br>
          MSc Computer Science, University of Exeter</p>
        `
      }
    )
    sheet.getRange(lastRow, pidCol + 1).setValue(pid)
    sheet.getRange(lastRow, conditionCol + 1).setValue(condition)
    sheet.getRange(lastRow, linkSentCol + 1).setValue("FAILED")
    sheet.getRange(lastRow, dateSentCol + 1).setValue(new Date().toISOString())
    Logger.log(`Registration failed for ${email} -- manual follow-up needed`)
    return
  }

  sheet.getRange(lastRow, pidCol + 1).setValue(pid)
  sheet.getRange(lastRow, conditionCol + 1).setValue(condition)
  sheet.getRange(lastRow, linkSentCol + 1).setValue("TRUE")
  sheet.getRange(lastRow, dateSentCol + 1).setValue(new Date().toISOString())

  GmailApp.sendEmail(
    email,
    "Your study link -- AI Coding Research Study",
    "",
    {
      name: YOUR_NAME,
      htmlBody: `
        <p>Hi ${firstName},</p>
        <p>Thank you for signing up for my MSc research
        study on AI coding tools.</p>
        <p>Your personal study link is below. This link
        is unique to you -- please do not share it with
        anyone else.</p>
        <p><a href="${studyLink}"
        style="font-size:16px; font-weight:bold;">
        Click here to begin the study</a></p>
        <p>Or copy this URL into your browser:<br>
        <code>${studyLink}</code></p>
        <p>The session takes approximately 30 to 45
        minutes and can be completed at any time that
        suits you. Please complete it on a device with
        a keyboard as you will need to write Python
        code.</p>
        <p>If you have any questions, reply to this
        email or contact me at
        <a href="mailto:${RESEARCHER_EMAIL}">${RESEARCHER_EMAIL}</a>.</p>
        <p>Thank you again for your help.<br><br>
        Best regards,<br>${YOUR_NAME}<br>
        MSc Computer Science, University of Exeter<br>
        ${RESEARCHER_EMAIL}</p>
      `
    }
  )

  Logger.log(`Study link sent to ${email} -- ${pid} (${condition})`)
}


// ====================================================
// PAYMENT — runs on an hourly time-based trigger
// Pays the first MAX_PAYMENTS participants who finish.
// ====================================================

const MAX_PAYMENTS = 56
const PAYMENT_GBP  = "5.00"
const PAYPAL_TOKEN_URL  = "https://api-m.paypal.com/v1/oauth2/token"
const PAYPAL_PAYOUT_URL = "https://api-m.paypal.com/v1/payments/payouts"

function checkAndPay() {
  const props         = PropertiesService.getScriptProperties()
  const backendUrl    = props.getProperty("BACKEND_URL")
  const monitoringKey = props.getProperty("MONITORING_API_KEY")
  const clientId      = props.getProperty("PAYPAL_CLIENT_ID")
  const clientSecret  = props.getProperty("PAYPAL_CLIENT_SECRET")

  if (!backendUrl || !clientId || !clientSecret) {
    Logger.log("ERROR: Missing Script Properties. Need BACKEND_URL, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET")
    return
  }

  // 1. Get PayPal OAuth token (valid for ~9 hours, fetch once per run)
  const token = _getPayPalToken(clientId, clientSecret)
  if (!token) {
    Logger.log("ERROR: Could not get PayPal access token. Check PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET.")
    return
  }

  // 2. Fetch completed PIDs from backend
  let completedPids
  try {
    const fetchOpts = { method: "GET", muteHttpExceptions: true }
    if (monitoringKey) fetchOpts.headers = { "x-api-key": monitoringKey }
    const res = UrlFetchApp.fetch(`${backendUrl}/participants/completions`, fetchOpts)
    if (res.getResponseCode() !== 200) {
      Logger.log(`ERROR: /participants/completions returned HTTP ${res.getResponseCode()}`)
      return
    }
    completedPids = new Set(
      JSON.parse(res.getContentText()).completions.map(c => c.participant_id)
    )
  } catch (err) {
    Logger.log(`ERROR: Failed to fetch completions: ${err}`)
    return
  }

  // 3. Fetch PayPal emails submitted by participants
  let paypalEmails
  try {
    const fetchOpts = { method: "GET", muteHttpExceptions: true }
    if (monitoringKey) fetchOpts.headers = { "x-api-key": monitoringKey }
    const res = UrlFetchApp.fetch(`${backendUrl}/participants/payment-emails`, fetchOpts)
    if (res.getResponseCode() !== 200) {
      Logger.log(`ERROR: /participants/payment-emails returned HTTP ${res.getResponseCode()}`)
      return
    }
    paypalEmails = JSON.parse(res.getContentText())  // { pid: paypal_email }
  } catch (err) {
    Logger.log(`ERROR: Failed to fetch payment emails: ${err}`)
    return
  }

  Logger.log(`Completed: ${completedPids.size} | PayPal emails received: ${Object.keys(paypalEmails).length}`)

  // 4. Read the Sheet for names and payment tracking
  const sheet   = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet()
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]

  const pidCol      = headers.indexOf("Participant_id")
  const nameCol     = headers.indexOf("What is your full name? ")
  const linkSentCol = headers.indexOf("link_sent")

  if (pidCol === -1 || nameCol === -1) {
    Logger.log("ERROR: Required Sheet columns not found (Participant_id / full name)")
    return
  }

  // Find or create payment_sent column
  let paymentSentCol = headers.indexOf("payment_sent")
  if (paymentSentCol === -1) {
    paymentSentCol = headers.length
    sheet.getRange(1, paymentSentCol + 1).setValue("payment_sent")
    Logger.log("Created payment_sent column")
  }

  // Count payments already sent
  let paymentsSent = 0
  for (let i = 1; i < data.length; i++) {
    if (data[i][paymentSentCol] === "TRUE") paymentsSent++
  }
  Logger.log(`Payments sent so far: ${paymentsSent} / ${MAX_PAYMENTS}`)

  // 5. Send payments
  for (let i = 1; i < data.length; i++) {
    const row           = data[i]
    const pid           = row[pidCol]
    const name          = row[nameCol] || "Participant"
    const firstName     = name.split(" ")[0]
    const linkSent      = row[linkSentCol]
    const paymentStatus = row[paymentSentCol]
    const paypalEmail   = paypalEmails[pid]

    if (!pid)                        continue  // empty row
    if (linkSent !== "TRUE")         continue  // never registered
    if (paymentStatus === "TRUE")    continue  // already paid
    if (paymentStatus === "FAILED")  continue  // failed — handle manually
    if (!completedPids.has(pid))     continue  // not finished yet
    if (!paypalEmail)                continue  // participant hasn't submitted PayPal email yet

    if (paymentsSent >= MAX_PAYMENTS) {
      Logger.log(`Payment cap of ${MAX_PAYMENTS} reached. Stopping.`)
      break
    }

    const success = _sendPayPalPayout(paypalEmail, firstName, pid, token)
    sheet.getRange(i + 1, paymentSentCol + 1).setValue(success ? "TRUE" : "FAILED")

    if (success) {
      paymentsSent++
      Logger.log(`Payment sent: ${pid} → ${paypalEmail}`)
    } else {
      Logger.log(`Payment FAILED: ${pid} → ${paypalEmail} — check logs and retry manually`)
    }

    Utilities.sleep(500)
  }

  Logger.log(`checkAndPay complete. Total paid: ${paymentsSent}`)
}


function _getPayPalToken(clientId, clientSecret) {
  const credentials = Utilities.base64Encode(`${clientId}:${clientSecret}`)
  try {
    const res = UrlFetchApp.fetch(PAYPAL_TOKEN_URL, {
      method:      "POST",
      contentType: "application/x-www-form-urlencoded",
      headers: {
        "Authorization":   `Basic ${credentials}`,
        "Accept":          "application/json",
        "Accept-Language": "en_US",
      },
      payload:            "grant_type=client_credentials",
      muteHttpExceptions: true,
    })
    if (res.getResponseCode() !== 200) {
      Logger.log(`PayPal token error: HTTP ${res.getResponseCode()} — ${res.getContentText()}`)
      return null
    }
    return JSON.parse(res.getContentText()).access_token
  } catch (err) {
    Logger.log(`PayPal token exception: ${err}`)
    return null
  }
}


function _sendPayPalPayout(paypalEmail, firstName, pid, token) {
  const payload = {
    sender_batch_header: {
      sender_batch_id: `scs_${pid}_${Date.now()}`,
      email_subject:   "Your AI Coding Study payment",
      email_message:   `Hi ${firstName}, thank you for completing the study. Here is your £5 payment.`,
    },
    items: [
      {
        recipient_type: "EMAIL",
        amount:         { value: PAYMENT_GBP, currency: "GBP" },
        receiver:       paypalEmail,
        sender_item_id: pid,
        note:           "Thank you for participating in the AI Coding Research Study.",
      },
    ],
  }

  try {
    const res = UrlFetchApp.fetch(PAYPAL_PAYOUT_URL, {
      method:             "POST",
      contentType:        "application/json",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept":        "application/json",
      },
      payload:            JSON.stringify(payload),
      muteHttpExceptions: true,
    })
    const code = res.getResponseCode()
    if (code === 201) return true
    Logger.log(`PayPal payout error for ${pid}: HTTP ${code} — ${res.getContentText()}`)
    return false
  } catch (err) {
    Logger.log(`PayPal payout exception for ${pid}: ${err}`)
    return false
  }
}
